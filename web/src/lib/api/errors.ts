import { z } from "zod";

export type FieldError = { loc: (string | number)[]; msg: string };

export class ApiError extends Error {
  readonly status: number;
  readonly title: string;
  readonly detail: string | null;
  readonly fieldErrors: FieldError[];

  constructor(status: number, title: string, detail: string | null = null, fieldErrors: FieldError[] = []) {
    super(`${status} ${title}${detail ? `: ${detail}` : ""}`);
    this.name = "ApiError";
    this.status = status;
    this.title = title;
    this.detail = detail;
    this.fieldErrors = fieldErrors;
  }
}

const problemSchema = z.object({
  title: z.string(),
  status: z.number().int(),
  detail: z.string().nullish(),
  errors: z
    .array(
      z.object({
        loc: z.array(z.union([z.string(), z.number()])).default([]),
        msg: z.string().default(""),
      }),
    )
    .nullish(),
});

export function problemToError(status: number, body: unknown): ApiError {
  const parsed = problemSchema.safeParse(body);
  if (parsed.success) {
    const p = parsed.data;
    return new ApiError(status, p.title, p.detail ?? null, (p.errors ?? []).map((e) => ({ loc: e.loc, msg: e.msg })));
  }
  return new ApiError(status, status >= 500 ? "Server error" : "Request failed");
}

export function networkError(cause: unknown): ApiError {
  const name = typeof cause === "object" && cause !== null && "name" in cause ? String((cause as { name: unknown }).name) : "";
  const timedOut = name === "TimeoutError" || name === "AbortError";
  return new ApiError(503, timedOut ? "Timed out" : "Unreachable", cause instanceof Error ? cause.message : null);
}

/** What a physician or reviewer reads. Never echoes stack traces or raw server text beyond problem fields. */
export function friendlyMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Something went wrong on our side. Try again in a moment.";
  switch (error.status) {
    case 503:
      if (error.title === "Timed out") return "The case service took too long to answer. Try again in a moment.";
      if (error.title === "Unreachable") return "We can't reach the case service right now. Try again in a minute.";
      return error.detail ?? "The model provider is unavailable right now. Try the other provider."; // API 503 names the provider
    case 404:
      return "This case doesn't exist, or it was removed.";
    case 401:
    case 403:
      return "The extraction service didn't accept this server's key.";
    case 413:
      return "That text is too long. Keep it under 20,000 characters.";
    case 422: {
      const first = error.fieldErrors.find((e) => e.msg)?.msg.replace(/\.$/, "");
      return first ? `The service rejected the input: ${first}.` : (error.detail ?? "The service rejected the input.");
    }
    case 429:
      return "Too many extractions, try again in a minute."; // only /api/extract is rate-limited
    case 502:
      return "The model returned output that didn't pass validation. Try again or switch provider.";
    default:
      return error.status >= 500 ? "The case service hit an error. Try again in a moment." : (error.detail ?? error.title);
  }
}
