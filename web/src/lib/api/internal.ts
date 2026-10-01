import "server-only";
import createClient from "openapi-fetch";
import { apiBaseUrl, internalApiKey, isFixtureMode } from "@/lib/env";
import { networkError, problemToError } from "./errors";
import * as fixtures from "./fixtures-internal";
import type { components, paths } from "./schema";
import type { CaseCreated, ClinicalCase } from "./types";

/*
 * Internal-key endpoints (★2 review gate, ★3 sponsor insights) and the studio's keyed publish.
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

function init() {
  const key = internalApiKey();
  return {
    cache: "no-store" as const,
    signal: AbortSignal.timeout(TIMEOUT_MS),
    headers: key ? { "X-Internal-Key": key } : {},
  };
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

export type ApproveOutcome = { status: "approved"; result: ApproveResponse } | { status: "already_approved" } | { status: "not_found" };

/** 409 (already approved, or a manual case) is an outcome, not an error: the caller sends the reviewer to the player. */
export async function approveCase(slug: string): Promise<ApproveOutcome> {
  if (isFixtureMode()) return fixtures.approve(slug);
  const { data, error, response } = await guard(() =>
    api().POST("/api/cases/{slug}/approve", { params: { path: { slug } }, ...init() }),
  );
  if (data !== undefined) return { status: "approved", result: data };
  if (response.status === 409) return { status: "already_approved" };
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
 * Studio publish. Sends the internal key because production sets REQUIRE_INGEST_KEY=true;
 * the caller forces `source.kind = "llm"`, so the API stores it as a draft.
 */
export async function publishDraft(body: ClinicalCase): Promise<CaseCreated> {
  if (isFixtureMode()) return fixtures.draftCreated;
  const { data, error, response } = await guard(() => api().POST("/api/cases", { body, ...init() }));
  if (data !== undefined) return data;
  throw problemToError(response.status, error);
}
