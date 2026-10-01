import "server-only";
import createClient from "openapi-fetch";
import { apiBaseUrl, internalApiKey, isFixtureMode } from "@/lib/env";
import { ApiError, friendlyMessage, networkError, problemToError } from "./errors";
import { attemptResultFor } from "./fixtures";
import * as fixtures from "./fixtures-internal";
import type { components, paths } from "./schema";
import type { AttemptIn, AttemptResult, CaseCreated, ClinicalCase } from "./types";

/*
 * Internal-key endpoints (★2 review gate, ★3 sponsor insights), the studio's keyed publish, and the
 * player's attempt (keyed so the API trusts the browser's address this server forwards for its throttle).
 * Same pattern as client.ts: server-only, typed by the generated schema, fixtures when
 * API_BASE_URL is unset. The key is read per request and never reaches the browser.
 */

type Schemas = components["schemas"];
export type CaseReview = Schemas["CaseReview"];
export type ReviewChecklistItem = Schemas["ReviewChecklistItem"];
export type CheckStatus = Schemas["CheckStatus"];
export type AnswerKey = Schemas["AnswerKey"];
export type AnswerKeyStage = Schemas["AnswerKeyStage"];
export type AnswerKeyOption = Schemas["AnswerKeyOption"];
export type ApproveResponse = Schemas["ApproveResponse"];
export type CaseInsights = Schemas["CaseInsights"];
export type InsightStage = Schemas["InsightStage"];
export type InsightOption = Schemas["InsightOption"];
export type KeyTestEffect = Schemas["KeyTestEffect"];
export type WrongDiagnosis = Schemas["WrongDiagnosis"];

const TIMEOUT_MS = 15_000;

/** The API's own sentence for a 429 (a per-minute window, the daily extraction budget, the daily draft cap). */
export function limitMessage(error: unknown): string | null {
  return error instanceof ApiError && error.status === 429 && error.detail ? error.detail : null;
}

/** friendlyMessage() words 401/403 for the extraction endpoint; these calls need their own wording. */
export function internalMessage(error: unknown): string {
  if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return "The case service didn't accept this server's key.";
  return limitMessage(error) ?? friendlyMessage(error);
}

function api() {
  const baseUrl = apiBaseUrl();
  if (baseUrl === null) throw new Error("API client used in fixture mode");
  return createClient<paths>({ baseUrl });
}

async function guard<T>(request: () => Promise<T>): Promise<T> {
  try {
    return await request();
  } catch (cause) {
    throw networkError(cause);
  }
}

function init(clientIp: string | null = null) {
  const key = internalApiKey();
  const headers: Record<string, string> = {};
  if (key) headers["X-Internal-Key"] = key;
  if (clientIp) headers["X-Forwarded-For"] = clientIp; // trusted by the API only next to the key
  return { cache: "no-store" as const, signal: AbortSignal.timeout(TIMEOUT_MS), headers };
}

/** The answer key and the server-computed checklist; `null` for an unknown slug. Works for any status. */
export async function getCaseReview(slug: string): Promise<CaseReview | null> {
  if (isFixtureMode()) return fixtures.reviewFor(slug);
  const { data, error, response } = await guard(() =>
    api().GET("/api/cases/{slug}/review", { params: { path: { slug } }, ...init() }),
  );
  if (data !== undefined) return data;
  if (response.status === 404) return null;
  throw problemToError(response.status, error);
}

export type ApproveOutcome =
  | { status: "approved"; result: ApproveResponse }
  | { status: "already_approved" }
  | { status: "blocked"; message: string }
  | { status: "not_found" };

const CHECKS_FAILING = "Review checks failing"; // backend/app/repository/review.py

/**
 * 409 is an outcome, not an error. "Already approved" (or a manual case): the caller sends the reviewer to
 * the player. A failing checklist item ("Review checks failing", recomputed by the API): the draft stays.
 */
export async function approveCase(slug: string): Promise<ApproveOutcome> {
  if (isFixtureMode()) return fixtures.approve(slug);
  const { data, error, response } = await guard(() =>
    api().POST("/api/cases/{slug}/approve", { params: { path: { slug } }, ...init() }),
  );
  if (data !== undefined) return { status: "approved", result: data };
  if (response.status === 409) {
    const problem = problemToError(409, error);
    if (problem.title === CHECKS_FAILING) return { status: "blocked", message: problem.detail ?? "A review check is failing." };
    return { status: "already_approved" };
  }
  if (response.status === 404) return { status: "not_found" };
  throw problemToError(response.status, error);
}

/** Cohort aggregates per decision point (humans + simulated cohort; AI players only as benchmarks). */
export async function getCaseInsights(slug: string): Promise<CaseInsights | null> {
  if (isFixtureMode()) return fixtures.insightsFor(slug);
  const { data, error, response } = await guard(() =>
    api().GET("/api/cases/{slug}/insights", { params: { path: { slug } }, ...init() }),
  );
  if (data !== undefined) return data;
  if (response.status === 404) return null;
  throw problemToError(response.status, error);
}

/**
 * Studio publish. Sends the internal key because production sets REQUIRE_INGEST_KEY=true. The body is the
 * API's own extraction (re-fetched by reference, never from the browser) with `source.kind = "llm"`, so the
 * API stores it as a draft and counts it against the daily draft cap.
 */
export async function publishDraft(body: ClinicalCase): Promise<CaseCreated> {
  if (isFixtureMode()) return fixtures.draftCreated;
  const { data, error, response } = await guard(() => api().POST("/api/cases", { body, ...init() }));
  if (data !== undefined) return data;
  throw problemToError(response.status, error);
}

/**
 * Closes a case. Keyed, with the browser's address: the API throttles attempts per client IP and trusts a
 * forwarded address only from a caller that holds the key (otherwise every player would share this server's).
 */
export async function recordAttempt(slug: string, body: AttemptIn, clientIp: string | null): Promise<AttemptResult> {
  if (isFixtureMode()) return attemptResultFor(slug, body);
  const { data, error, response } = await guard(() =>
    api().POST("/api/cases/{slug}/attempts", { params: { path: { slug } }, body, ...init(clientIp) }),
  );
  if (data !== undefined) return data;
  throw problemToError(response.status, error);
}
