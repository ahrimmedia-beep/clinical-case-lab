import { describe, expect, it } from "vitest";
import { ApiError, friendlyMessage, networkError, problemToError } from "./errors";

describe("problemToError", () => {
  it("reads RFC 9457 problem+json with field errors", () => {
    const err = problemToError(422, {
      type: "about:blank",
      title: "Validation failed",
      status: 422,
      errors: [{ loc: ["body", "choices", "workup", 0], msg: "String should match pattern '^[A-L]$'", type: "string_pattern_mismatch" }],
    });
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.title).toBe("Validation failed");
    expect(err.fieldErrors[0]).toEqual({ loc: ["body", "choices", "workup", 0], msg: "String should match pattern '^[A-L]$'" });
  });

  it("falls back to a generic title for non-problem bodies", () => {
    const err = problemToError(502, "<html>Bad gateway</html>");
    expect(err.status).toBe(502);
    expect(err.title).toBe("Server error");
  });
});

describe("networkError", () => {
  it("maps refused connections and timeouts to 503", () => {
    expect(networkError(new TypeError("fetch failed"))).toMatchObject({ status: 503, title: "Unreachable" });
    const timeout = new Error("The operation was aborted due to timeout");
    timeout.name = "TimeoutError";
    expect(networkError(timeout)).toMatchObject({ status: 503, title: "Timed out" });
  });
});

describe("friendlyMessage", () => {
  it("speaks plainly for each failure class", () => {
    expect(friendlyMessage(new ApiError(503, "Unreachable"))).toMatch(/can't reach the case service/);
    expect(friendlyMessage(new ApiError(503, "Timed out"))).toMatch(/took too long/);
    expect(friendlyMessage(new ApiError(404, "Not found"))).toMatch(/doesn't exist/);
    expect(friendlyMessage(new ApiError(429, "Too many requests"))).toBe("Too many extractions, try again in a minute.");
    expect(friendlyMessage(new ApiError(503, "Provider unavailable", "Claude on Vertex AI is unavailable right now."))).toBe(
      "Claude on Vertex AI is unavailable right now.",
    );
    expect(friendlyMessage(new ApiError(500, "Internal server error"))).toMatch(/hit an error/);
    expect(friendlyMessage(new Error("boom"))).toMatch(/Something went wrong/);
  });

  it("surfaces the first validation message on 422", () => {
    const err = new ApiError(422, "Validation failed", null, [{ loc: ["body"], msg: "Value error, title leaks the diagnosis." }]);
    expect(friendlyMessage(err)).toBe("The service rejected the input: Value error, title leaks the diagnosis.");
  });
});
