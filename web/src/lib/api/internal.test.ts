import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { approveCase, internalMessage, recordAttempt } from "./internal";
import { ApiError } from "./errors";

const fetchMock = vi.fn<(request: Request) => Promise<Response>>();

function problem(status: number, title: string, detail: string): Response {
  return new Response(JSON.stringify({ type: "about:blank", title, status, detail }), {
    status,
    headers: { "content-type": "application/problem+json" },
  });
}

beforeEach(() => {
  vi.stubEnv("API_BASE_URL", "http://api.test");
  vi.stubEnv("INTERNAL_API_KEY", "k3y");
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

describe("approveCase", () => {
  it("tells a failing check (blocked) apart from an already approved case", async () => {
    fetchMock.mockResolvedValueOnce(problem(409, "Review checks failing", "Approval is blocked while a check fails: No answer before the debrief."));
    expect(await approveCase("lam-draft-1a2b3c")).toEqual({
      status: "blocked",
      message: "Approval is blocked while a check fails: No answer before the debrief.",
    });
    fetchMock.mockResolvedValueOnce(problem(409, "Already approved", "Case 'lam-draft-1a2b3c' is already approved."));
    expect(await approveCase("lam-draft-1a2b3c")).toEqual({ status: "already_approved" });
  });
});

describe("recordAttempt", () => {
  it("sends the key and names the browser's address, so the API's per-IP throttle sees people", async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ attempt_id: 1 }), { status: 201, headers: { "content-type": "application/json" } }));
    await recordAttempt("pe-case-1a2b3c", { choices: {}, diagnosis_text: "PE", confidence: 3, duration_ms: null }, "203.0.113.7");
    const request = fetchMock.mock.calls[0][0];
    expect(request.url).toBe("http://api.test/api/cases/pe-case-1a2b3c/attempts");
    expect(request.headers.get("X-Internal-Key")).toBe("k3y");
    expect(request.headers.get("X-Forwarded-For")).toBe("203.0.113.7");
  });

  it("surfaces the throttle as an ApiError 429", async () => {
    fetchMock.mockResolvedValueOnce(problem(429, "Too many requests", "At most 20 attempts per minute; retry in 12 s."));
    await expect(recordAttempt("pe-case-1a2b3c", { choices: {}, diagnosis_text: "PE", confidence: 3, duration_ms: null }, null)).rejects.toMatchObject({
      status: 429,
    });
  });
});

describe("internalMessage", () => {
  it("shows the API's own sentence for a limit, and a fixed one for a bad key", () => {
    expect(internalMessage(new ApiError(429, "Draft limit reached", "At most 20 AI drafts can be published per day (UTC); try again tomorrow."))).toBe(
      "At most 20 AI drafts can be published per day (UTC); try again tomorrow.",
    );
    expect(internalMessage(new ApiError(401, "Unauthorized"))).toBe("The case service didn't accept this server's key.");
  });
});
