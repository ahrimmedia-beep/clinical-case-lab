import { afterEach, describe, expect, it, vi } from "vitest";
import { IDLE_EXTRACT } from "@/lib/action-states";
import { extractResponse } from "@/lib/api/fixtures";
import { ApiError } from "@/lib/api/errors";
import { extractCase, publishCase } from "./actions";

const redirect = vi.fn();
const publishDraft = vi.fn();
const extract = vi.fn();

vi.mock("next/navigation", () => ({ redirect: (path: string) => redirect(path) }));
vi.mock("next/headers", () => ({ headers: async () => new Headers({ "x-forwarded-for": "10.9.8.7, 203.0.113.7" }) }));
vi.mock("@/lib/api/internal", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/internal")>()),
  publishDraft: (body: unknown) => publishDraft(body),
}));
vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return { ...actual, extractCase: (...args: Parameters<typeof actual.extractCase>) => extract(...args) };
});

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
  extract.mockReset();
});

describe("extractCase", () => {
  it("forwards the end user's IP (the last X-Forwarded-For entry) for the API's per-IP limit", async () => {
    extract.mockResolvedValue(extractResponse);
    const state = await extractCase(IDLE_EXTRACT, form({ text: "x".repeat(80), provider: "gemini" }));
    expect(state.status).toBe("done");
    expect(extract).toHaveBeenCalledWith({ text: "x".repeat(80), provider: "gemini", model: null }, "203.0.113.7");
  });

  it("shows the API's own words when a limit is hit (per minute or for the day)", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    extract.mockRejectedValue(new ApiError(429, "Too many requests", "The daily extraction budget is used up; try again tomorrow (UTC)."));
    const state = await extractCase(IDLE_EXTRACT, form({ text: "x".repeat(80), provider: "gemini" }));
    expect(state).toMatchObject({ status: "error", message: "The daily extraction budget is used up; try again tomorrow (UTC)." });
  });

  it("explains a too-short text without calling the API", async () => {
    vi.stubEnv("API_BASE_URL", "http://127.0.0.1:9");
    const state = await extractCase(IDLE_EXTRACT, form({ text: "short", provider: "gemini" }));
    expect(state).toMatchObject({ status: "error" });
    if (state.status === "error") expect(state.fieldErrors.text?.[0]).toMatch(/at least 50/);
  });

  it("turns an unreachable API into a calm message", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    extract.mockRejectedValue(new ApiError(503, "Unreachable"));
    const state = await extractCase(IDLE_EXTRACT, form({ text: "x".repeat(80), provider: "claude" }));
    expect(state).toMatchObject({ status: "error", message: expect.stringContaining("can't reach the case service") });
  });
});

describe("publishCase", () => {
  const request = { text: "x".repeat(80), provider: "gemini", model: "gemini-3.8-flash" } as const;

  it("re-runs the extraction by reference and stores the server's own result as an AI draft", async () => {
    // The studio's extraction is cached, so this is a free, instant cache hit on the API.
    const manual = { ...extractResponse, case: { ...extractResponse.case, source: { kind: "manual" as const, provider: "gemini", text: null } } };
    extract.mockResolvedValue(manual);
    publishDraft.mockResolvedValue({ id: 7, slug: "new-draft-abc123", created: true });
    await publishCase(request);
    expect(extract).toHaveBeenCalledWith({ text: "x".repeat(80), provider: "gemini", model: "gemini-3.8-flash" }, "203.0.113.7");
    expect(publishDraft).toHaveBeenCalledOnce();
    const stored = publishDraft.mock.calls[0][0];
    expect(stored.title).toBe(extractResponse.case.title);
    // Always a draft, and the de-identified text travels with it for the review's grounding check.
    expect(stored.source).toMatchObject({ kind: "llm", provider: "gemini", text: extractResponse.source_text });
    expect(redirect).toHaveBeenCalledWith("/cases/new-draft-abc123/review");
  });

  it("refuses anything but a text, a provider and a model, without calling the API", async () => {
    const tampered = [JSON.stringify(extractResponse.case), { ...request, case: extractResponse.case }, { ...request, text: "short" }, null];
    for (const input of tampered) {
      expect(await publishCase(input as never)).toEqual({ status: "error", message: "This draft can't be published. Extract it again." });
    }
    expect(extract).not.toHaveBeenCalled();
    expect(publishDraft).not.toHaveBeenCalled();
    expect(redirect).not.toHaveBeenCalled();
  });

  it("explains an API rejection or a limit and stays on the page", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    extract.mockResolvedValue(extractResponse);
    publishDraft.mockRejectedValue(new ApiError(422, "Validation failed", null, [{ loc: ["body", "title"], msg: "Title names the diagnosis." }]));
    expect(await publishCase(request)).toEqual({ status: "error", message: "The service rejected the input: Title names the diagnosis." });
    publishDraft.mockRejectedValue(new ApiError(401, "Unauthorized"));
    expect(await publishCase(request)).toMatchObject({ message: "The case service didn't accept this server's key." });
    publishDraft.mockRejectedValue(new ApiError(429, "Draft limit reached", "At most 20 AI drafts can be published per day (UTC); try again tomorrow."));
    expect(await publishCase(request)).toMatchObject({ message: "At most 20 AI drafts can be published per day (UTC); try again tomorrow." });
    expect(redirect).not.toHaveBeenCalled();
  });
});
