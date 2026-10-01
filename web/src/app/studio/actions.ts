"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import type { ExtractState, PublishState } from "@/lib/action-states";
import * as api from "@/lib/api/client";
import { ApiError, friendlyMessage } from "@/lib/api/errors";
import { publishDraft } from "@/lib/api/internal";
import type { ClinicalCase } from "@/lib/api/types";
import { clientIp, parseExtractForm } from "@/lib/forms";

const MAX_CASE_JSON_CHARS = 256 * 1024; // the API's body limit for POST /api/cases

/** Raw text → de-identify → extract → ground → author → validate, all on the API. Never throws. */
export async function extractCase(_prev: ExtractState, formData: FormData): Promise<ExtractState> {
  const parsed = parseExtractForm(formData);
  if (!parsed.ok) return { status: "error", message: "Check the text and the model.", fieldErrors: parsed.fieldErrors };
  try {
    const ip = clientIp(await headers()); // per-IP rate limit on the API sees the end user, not this server
    return { status: "done", result: await api.extractCase(parsed.value, ip) };
  } catch (error) {
    console.error("extractCase failed", { provider: parsed.value.provider, error: String(error) });
    return { status: "error", message: friendlyMessage(error), fieldErrors: {} };
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Whatever arrives from the browser is stored as an AI draft: `source.kind` is forced to "llm", so the
 * API sets review_status = draft and the case needs a physician's approval before it counts.
 */
function asDraft(raw: Record<string, unknown>): ClinicalCase {
  const source = isRecord(raw.source) ? raw.source : {};
  const str = (v: unknown) => (typeof v === "string" && v.length > 0 ? v : null);
  return {
    ...(raw as unknown as ClinicalCase),
    source: { kind: "llm", provider: str(source.provider), model: str(source.model), prompt_version: str(source.prompt_version), text: str(source.text) },
  };
}

/** Publishes the studio's extracted case as a draft and opens its physician review. The API re-validates everything. */
export async function publishCase(caseJson: string): Promise<PublishState> {
  if (typeof caseJson !== "string" || caseJson.length > MAX_CASE_JSON_CHARS) {
    return { status: "error", message: "The extracted case is too large to publish." };
  }
  let slug: string;
  try {
    const parsed: unknown = JSON.parse(caseJson);
    if (!isRecord(parsed)) return { status: "error", message: "The extracted case is malformed." };
    slug = (await publishDraft(asDraft(parsed))).slug;
  } catch (error) {
    if (error instanceof SyntaxError) return { status: "error", message: "The extracted case is malformed." };
    console.error("publishCase failed", { error: String(error) });
    const keyProblem = error instanceof ApiError && (error.status === 401 || error.status === 403);
    return { status: "error", message: keyProblem ? "The case service didn't accept this server's key." : friendlyMessage(error) };
  }
  redirect(`/cases/${slug}/review`); // outside try: redirect() works by throwing
}
