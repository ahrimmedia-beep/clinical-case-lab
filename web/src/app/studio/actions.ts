"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import type { ExtractState, PublishState } from "@/lib/action-states";
import * as api from "@/lib/api/client";
import { friendlyMessage } from "@/lib/api/errors";
import { internalMessage, limitMessage, publishDraft } from "@/lib/api/internal";
import type { ClinicalCase, ExtractRequest, ExtractResponse } from "@/lib/api/types";
import { clientIp, parseExtractForm, parsePublishInput } from "@/lib/forms";

const SOURCE_TEXT_MAX = 20_000; // CaseSource.text max_length on the API

/** Raw text → de-identify → extract → ground → author → validate, all on the API. Never throws. */
export async function extractCase(_prev: ExtractState, formData: FormData): Promise<ExtractState> {
  const parsed = parseExtractForm(formData);
  if (!parsed.ok) return { status: "error", message: "Check the text and the model.", fieldErrors: parsed.fieldErrors };
  try {
    const ip = clientIp(await headers()); // per-IP rate limit on the API sees the end user, not this server
    return { status: "done", result: await api.extractCase(parsed.value, ip) };
  } catch (error) {
    console.error("extractCase failed", { provider: parsed.value.provider, error: String(error) });
    return { status: "error", message: limitMessage(error) ?? friendlyMessage(error), fieldErrors: {} };
  }
}

/**
 * The API's extraction, stored as an AI draft: `source.kind` is forced to "llm", so the API sets
 * review_status = draft and the case needs a physician's approval before it counts. The de-identified text
 * travels with it: the review checklist re-checks every quote against it.
 */
function asDraft(extraction: ExtractResponse): ClinicalCase {
  const source = extraction.case.source;
  const fallback = extraction.source_text.length <= SOURCE_TEXT_MAX ? extraction.source_text : null;
  return {
    ...extraction.case,
    source: {
      kind: "llm",
      provider: source?.provider ?? extraction.provider,
      model: source?.model ?? extraction.model,
      prompt_version: source?.prompt_version ?? extraction.prompt_version,
      text: source?.text ?? fallback,
    },
  };
}

/**
 * Publishes by reference, never by content: the browser sends back only what it asked to extract (text,
 * provider, model). This server re-runs that extraction on the API (a cache hit: instant, free, outside the
 * rate limit), publishes the API's own result as a draft, and opens its physician review.
 */
export async function publishCase(request: ExtractRequest): Promise<PublishState> {
  const parsed = parsePublishInput(request);
  if (!parsed.ok) return { status: "error", message: "This draft can't be published. Extract it again." };
  let slug: string;
  try {
    const extraction = await api.extractCase(parsed.value, clientIp(await headers()));
    slug = (await publishDraft(asDraft(extraction))).slug;
  } catch (error) {
    console.error("publishCase failed", { provider: parsed.value.provider, error: String(error) });
    return { status: "error", message: internalMessage(error) };
  }
  redirect(`/cases/${slug}/review`); // outside try: redirect() works by throwing
}
