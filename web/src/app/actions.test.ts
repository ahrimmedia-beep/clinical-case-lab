import { afterEach, describe, expect, it, vi } from "vitest";
import { IDLE_SUBMIT } from "@/lib/action-states";
import { peCasePublic } from "@/lib/api/fixtures";
import { revealOptions, submitAttempt } from "./actions";

const setCookie = vi.fn();

vi.mock("next/headers", () => ({
  headers: async () => new Headers({ "x-forwarded-for": "203.0.113.7, 10.0.0.1" }),
  cookies: async () => ({ set: setCookie }),
}));

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
});

describe("submitAttempt", () => {
  it("returns the debrief in fixture mode", async () => {
    vi.stubEnv("API_BASE_URL", "");
    vi.spyOn(console, "info").mockImplementation(() => undefined);
    const state = await submitAttempt(peCasePublic.slug, IDLE_SUBMIT, form(attempt));
    expect(state.status).toBe("done");
    if (state.status === "done") expect(state.result.diagnosis.your_text).toBe("Pulmonary embolism");
  });

  it("sets an httpOnly closed_<slug> cookie once the attempt is recorded", async () => {
    vi.stubEnv("API_BASE_URL", "");
    vi.spyOn(console, "info").mockImplementation(() => undefined);
    await submitAttempt(peCasePublic.slug, IDLE_SUBMIT, form(attempt));
    expect(setCookie).toHaveBeenCalledWith(
      `closed_${peCasePublic.slug}`,
      "1",
      expect.objectContaining({ httpOnly: true, path: "/" }),
    );
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
