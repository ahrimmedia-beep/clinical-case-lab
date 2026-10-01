import "server-only";
import createClient from "openapi-fetch";
import { apiBaseUrl, internalApiKey, isFixtureMode } from "@/lib/env";
import { networkError, problemToError } from "./errors";
import * as fixtures from "./fixtures";
import type { paths } from "./schema";
import type {
  CasePublic,
  CaseSummary,
  ExtractRequest,
  ExtractResponse,
  RevealIn,
  RevealOut,
} from "./types";

export { isFixtureMode };

const READ_TIMEOUT_MS = 15_000;
const EXTRACT_TIMEOUT_MS = 120_000; // two model calls plus a repair round

/** Built per call so API_BASE_URL is read at request time (one image, many environments). */
function api() {
  const baseUrl = apiBaseUrl();
  if (baseUrl === null) throw new Error("API client used in fixture mode");
  return createClient<paths>({ baseUrl });
}

/** Refused connections, DNS failures and timeouts become ApiError 503 instead of a raw TypeError. */
async function guard<T>(request: () => Promise<T>): Promise<T> {
  try {
    return await request();
  } catch (cause) {
    throw networkError(cause);
  }
}

function init(timeoutMs = READ_TIMEOUT_MS) {
  return { cache: "no-store" as const, signal: AbortSignal.timeout(timeoutMs) };
}

export async function listCases(): Promise<CaseSummary[]> {
  if (isFixtureMode()) return fixtures.caseSummaries;
  const { data, error, response } = await guard(() => api().GET("/api/cases", init()));
  if (data !== undefined) return data;
  throw problemToError(response.status, error);
}

export async function getCase(slug: string): Promise<CasePublic | null> {
  if (isFixtureMode()) return fixtures.findCase(slug);
  const { data, error, response } = await guard(() =>
    api().GET("/api/cases/{slug}", { params: { path: { slug } }, ...init() }),
  );
  if (data !== undefined) return data;
  if (response.status === 404) return null;
  throw problemToError(response.status, error);
}

export async function revealOptions(slug: string, body: RevealIn): Promise<RevealOut[]> {
  if (isFixtureMode()) return fixtures.revealsFor(slug, body);
  const { data, error, response } = await guard(() =>
    api().POST("/api/cases/{slug}/reveal", { params: { path: { slug } }, body, ...init() }),
  );
  if (data !== undefined) return data;
  throw problemToError(response.status, error);
}

/** `clientIp` is the end user's address, forwarded so the API's per-IP rate limit sees people, not this server. */
export async function extractCase(body: ExtractRequest, clientIp: string | null = null): Promise<ExtractResponse> {
  if (isFixtureMode()) return fixtures.extractResponse;
  const key = internalApiKey();
  const headers: Record<string, string> = {};
  if (key) headers["X-Internal-Key"] = key; // the only call in this file that carries the key; lib/api/internal.ts has its own key-bearing calls
  if (clientIp) headers["X-Forwarded-For"] = clientIp;
  const { data, error, response } = await guard(() =>
    api().POST("/api/extract", { body, headers, ...init(EXTRACT_TIMEOUT_MS) }),
  );
  if (data !== undefined) return data;
  throw problemToError(response.status, error);
}
