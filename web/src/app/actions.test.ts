import { afterEach, describe, expect, it, vi } from "vitest";
import { IDLE_SUBMIT } from "@/lib/action-states";
import { ApiError } from "@/lib/api/errors";
import { peCasePublic } from "@/lib/api/fixtures";
import { verifyClosedCookie } from "@/lib/closed-cookie";
import { revealOptions, submitAttempt } from "./actions";

const setCookie = vi.fn();
const record = vi.fn();

vi.mock("next/headers", () => ({
  headers: async () => new Headers({ "x-forwarded-for": "10.9.8.7, 203.0.113.7" }),
  cookies: async () => ({ set: setCookie }),
}));
vi.mock("@/lib/api/internal", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/internal")>();
  return { ...actual, recordAttempt: (...args: Parameters<typeof actual.recordAttempt>) => record(...args) };
});

function form(fields: Record<string, string>): FormData {
  const fd = new FormData();
  for (const [key, value] of Object.entries(fields)) fd.set(key, value);
  return fd;
}

const attempt = {
  choices: JSON.stringify({ workup: ["A", "B"] }),
  diagnosis_text: "Pulmonary embolism",
  confidence: "4",
  duration_ms: "61000",
};

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  setCookie.mockClear();
  record.mockReset();
});

async function recordForReal(...args: unknown[]) {
  const actual = await vi.importActual<typeof import("@/lib/api/internal")>("@/lib/api/internal");
  return actual.recordAttempt(...(args as Parameters<typeof actual.recordAttempt>));
}

describe("submitAttempt", () => {
  it("returns the debrief in fixture mode", async () => {
    vi.stubEnv("API_BASE_URL", "");
    vi.spyOn(console, "info").mockImplementation(() => undefined);
    record.mockImplementation(recordForReal);
    const state = await submitAttempt(peCasePublic.slug, IDLE_SUBMIT, form(attempt));
    expect(state.status).toBe("done");
    if (state.status === "done") expect(state.result.diagnosis.your_text).toBe("Pulmonary embolism");
  });

  it("forwards the end user's IP (last X-Forwarded-For entry) for the API's per-IP throttle", async () => {
    vi.stubEnv("API_BASE_URL", "");
    vi.spyOn(console, "info").mockImplementation(() => undefined);
    record.mockImplementation(recordForReal);
    await submitAttempt(peCasePublic.slug, IDLE_SUBMIT, form(attempt));
    expect(record).toHaveBeenCalledWith(peCasePublic.slug, expect.objectContaining({ diagnosis_text: "Pulmonary embolism" }), "203.0.113.7");
  });

  it("sets a signed, httpOnly closed_<slug> cookie once the attempt is recorded", async () => {
    vi.stubEnv("API_BASE_URL", "");
    vi.stubEnv("INTERNAL_API_KEY", "k3y");
    vi.spyOn(console, "info").mockImplementation(() => undefined);
    record.mockImplementation(recordForReal);
    const state = await submitAttempt(peCasePublic.slug, IDLE_SUBMIT, form(attempt));
    expect(setCookie).toHaveBeenCalledWith(
      `closed_${peCasePublic.slug}`,
      expect.any(String),
      expect.objectContaining({ httpOnly: true, sameSite: "lax", path: "/", secure: false }),
    );
    const value: string = setCookie.mock.calls[0][1];
    expect(state.status === "done" && value.startsWith(`${state.result.attempt_id}.`)).toBe(true);
    expect(verifyClosedCookie(peCasePublic.slug, value)).toBe(true);
    expect(verifyClosedCookie("another-case-1a2b3c", value)).toBe(false);
  });

  it("marks the cookie Secure in production", async () => {
    vi.stubEnv("API_BASE_URL", "");
    vi.stubEnv("NODE_ENV", "production");
    vi.spyOn(console, "info").mockImplementation(() => undefined);
    record.mockImplementation(recordForReal);
    await submitAttempt(peCasePublic.slug, IDLE_SUBMIT, form(attempt));
    expect(setCookie.mock.calls[0][2]).toMatchObject({ secure: true });
  });

  it("explains the attempt throttle without setting the cookie", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    record.mockRejectedValue(new ApiError(429, "Too many requests", "At most 20 attempts per minute; retry in 12 s."));
    const state = await submitAttempt(peCasePublic.slug, IDLE_SUBMIT, form(attempt));
    expect(state).toMatchObject({ status: "error", message: "Too many cases closed from this network in a minute. Try again shortly." });
    expect(setCookie).not.toHaveBeenCalled();
  });

  it("returns field errors without calling the API", async () => {
    vi.stubEnv("API_BASE_URL", "http://127.0.0.1:9");
    const state = await submitAttempt(peCasePublic.slug, IDLE_SUBMIT, form({ ...attempt, diagnosis_text: "" }));
    expect(state).toMatchObject({ status: "error", message: "Some answers need another look." });
    if (state.status === "error") expect(state.fieldErrors.diagnosis_text).toBeDefined();
    expect(setCookie).not.toHaveBeenCalled();
  });

  it("rejects a malformed slug", async () => {
    const state = await submitAttempt("../admin", IDLE_SUBMIT, form(attempt));
    expect(state).toMatchObject({ status: "error", message: "This case link is not valid." });
  });

  it("turns an unreachable API into a calm message instead of throwing", async () => {
    vi.stubEnv("API_BASE_URL", "http://127.0.0.1:9");
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    record.mockImplementation(recordForReal);
    const state = await submitAttempt(peCasePublic.slug, IDLE_SUBMIT, form(attempt));
    expect(state).toMatchObject({ status: "error", message: expect.stringContaining("can't reach the case service") });
    expect(setCookie).not.toHaveBeenCalled();
  });
});

describe("revealOptions", () => {
  it("returns reveals for a valid interview/workup selection in fixture mode", async () => {
    vi.stubEnv("API_BASE_URL", "");
    const result = await revealOptions(peCasePublic.slug, "workup", ["A", "B"]);
    expect(result.status).toBe("ok");
    if (result.status === "ok") expect(result.reveals.map((r) => r.key)).toEqual(["A", "B"]);
  });

  it("rejects a stage that has no reveals", async () => {
    vi.stubEnv("API_BASE_URL", "");
    const result = await revealOptions(peCasePublic.slug, "treatment", ["A"]);
    expect(result.status).toBe("error");
  });
});
