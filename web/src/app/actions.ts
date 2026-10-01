"use server";

import { cookies, headers } from "next/headers";
import type { RevealResult, SubmitState } from "@/lib/action-states";
import * as api from "@/lib/api/client";
import { ApiError, friendlyMessage } from "@/lib/api/errors";
import { recordAttempt } from "@/lib/api/internal";
import { closedCookieValue } from "@/lib/closed-cookie";
import { clientIp, isValidSlug, parseAttemptForm, parseRevealInput } from "@/lib/forms";

// Note on scope (amendments §E, track split): `extractCase` and `publishCase` are studio-only
// Server Actions and live in `app/studio/actions.ts` (track C2), which owns `app/studio/**`.
// This file carries only the actions the case player (owned by C1) needs.

const CLOSED_COOKIE_MAX_AGE_S = 60 * 60 * 24 * 30; // 30 days: long enough to revisit a closed case's insights

/** Closes the case: validates the answers, the API scores them, the debrief comes back. Never throws. */
export async function submitAttempt(slug: string, _prev: SubmitState, formData: FormData): Promise<SubmitState> {
  if (!isValidSlug(slug)) return { status: "error", message: "This case link is not valid.", fieldErrors: {} };
  const parsed = parseAttemptForm(formData);
  if (!parsed.ok) return { status: "error", message: "Some answers need another look.", fieldErrors: parsed.fieldErrors };
  try {
    // The browser's address goes along so the API's per-IP attempt throttle sees people, not this server.
    const result = await recordAttempt(slug, parsed.value, clientIp(await headers()));
    // Signed marker (attempt id + HMAC, lib/closed-cookie.ts) that this browser closed this case, so the
    // sponsor-only insights page (/cases/{slug}/insights) can gate on having played it.
    const jar = await cookies();
    jar.set(`closed_${slug}`, closedCookieValue(slug, result.attempt_id), {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: CLOSED_COOKIE_MAX_AGE_S,
    });
    return { status: "done", result };
  } catch (error) {
    // Log the failure class only: never the answers.
    console.error("submitAttempt failed", { slug, error: String(error) });
    const throttled = error instanceof ApiError && error.status === 429;
    const message = throttled ? "Too many cases closed from this network in a minute. Try again shortly." : friendlyMessage(error);
    return { status: "error", message, fieldErrors: {} };
  }
}

/** After an interview or workup stage is locked: the patient's answers / test results for the chosen options. */
export async function revealOptions(slug: string, stage: string, keys: string[]): Promise<RevealResult> {
  const parsed = parseRevealInput(slug, stage, keys);
  if (!parsed.ok) return { status: "error", message: "These answers can't be shown." };
  try {
    return { status: "ok", reveals: await api.revealOptions(parsed.value.slug, parsed.value.body) };
  } catch (error) {
    return { status: "error", message: friendlyMessage(error) };
  }
}
