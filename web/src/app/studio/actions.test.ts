import { afterEach, describe, expect, it, vi } from "vitest";
import { IDLE_EXTRACT } from "@/lib/action-states";
import { extractResponse } from "@/lib/api/fixtures";
import { ApiError } from "@/lib/api/errors";
import { extractCase, publishCase } from "./actions";

const redirect = vi.fn();
const publishDraft = vi.fn();

vi.mock("next/navigation", () => ({ redirect: (path: string) => redirect(path) }));
vi.mock("next/headers", () => ({ headers: async () => new Headers({ "x-forwarded-for": "203.0.113.7, 10.0.0.1" }) }));
vi.mock("@/lib/api/internal", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/internal")>()),
  publishDraft: (body: unknown) => publishDraft(body),
}));

function form(fields: Record<string, string>): FormData {
  const fd = new FormData();
  for (const [key, value] of Object.entries(fields)) fd.set(key, value);
  return fd;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  redirect.mockReset();
  publishDraft.mockReset();
});

describe("extractCase", () => {
  it("returns the extraction in fixture mode", async () => {
    vi.stubEnv("API_BASE_URL", "");
    const state = await extractCase(IDLE_EXTRACT, form({ text: "x".repeat(80), provider: "gemini" }));
    expect(state.status).toBe("done");
  });

  it("explains a too-short text without calling the API", async () => {
    vi.stubEnv("API_BASE_URL", "http://127.0.0.1:9");
    const state = await extractCase(IDLE_EXTRACT, form({ text: "short", provider: "gemini" }));
    expect(state).toMatchObject({ status: "error" });
    if (state.status === "error") expect(state.fieldErrors.text?.[0]).toMatch(/at least 50/);
  });

  it("turns an unreachable API into a calm message", async () => {
    vi.stubEnv("API_BASE_URL", "http://127.0.0.1:9");
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const state = await extractCase(IDLE_EXTRACT, form({ text: "x".repeat(80), provider: "claude" }));
    expect(state).toMatchObject({ status: "error", message: expect.stringContaining("can't reach the case service") });
  });
});

describe("publishCase", () => {
  it("stores whatever it receives as an AI draft and opens the review", async () => {
    publishDraft.mockResolvedValue({ id: 7, slug: "new-draft-abc123", created: true });
    const tampered = { ...extractResponse.case, source: { kind: "manual", provider: "gemini", model: "gemini-3.8-flash", prompt_version: "v1", text: "de-identified" } };
    await publishCase(JSON.stringify(tampered));
    expect(publishDraft).toHaveBeenCalledOnce();
    expect(publishDraft.mock.calls[0][0].source).toEqual({
      kind: "llm",
      provider: "gemini",
      model: "gemini-3.8-flash",
      prompt_version: "v1",
      text: "de-identified",
    });
    expect(redirect).toHaveBeenCalledWith("/cases/new-draft-abc123/review");
  });

  it("refuses malformed or oversized input without calling the API", async () => {
    expect(await publishCase("{not json")).toEqual({ status: "error", message: "The extracted case is malformed." });
    expect(await publishCase("[1,2]")).toEqual({ status: "error", message: "The extracted case is malformed." });
    expect(await publishCase("x".repeat(300_000))).toMatchObject({ status: "error", message: expect.stringContaining("too large") });
    expect(publishDraft).not.toHaveBeenCalled();
    expect(redirect).not.toHaveBeenCalled();
  });

  it("explains an API rejection and stays on the page", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    publishDraft.mockRejectedValue(new ApiError(422, "Validation failed", null, [{ loc: ["body", "title"], msg: "Title names the diagnosis." }]));
    expect(await publishCase(JSON.stringify(extractResponse.case))).toEqual({
      status: "error",
      message: "The service rejected the input: Title names the diagnosis.",
    });
    publishDraft.mockRejectedValue(new ApiError(401, "Unauthorized"));
    expect(await publishCase(JSON.stringify(extractResponse.case))).toMatchObject({ message: "The case service didn't accept this server's key." });
    expect(redirect).not.toHaveBeenCalled();
  });
});
