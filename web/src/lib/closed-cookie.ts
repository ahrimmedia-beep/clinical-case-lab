import "server-only";
import { createHmac, timingSafeEqual } from "node:crypto";
import { internalApiKey } from "@/lib/env";

/*
 * The `closed_<slug>` cookie that opens a case's sponsor view: "<attempt id>.<HMAC-SHA256 of slug and
 * attempt id>", keyed with this server's INTERNAL_API_KEY. A hand-made cookie, or one copied to another
 * case, fails the check. It proves this browser closed the case here, not who the player is.
 */

// Only when INTERNAL_API_KEY is unset: local development and fixture mode, where the API is open anyway.
const LOCAL_SECRET = "case-lab-local-only";
const VALUE = /^(\d{1,19})\.([A-Za-z0-9_-]{43})$/;

function mac(slug: string, attemptId: string): string {
  return createHmac("sha256", internalApiKey() ?? LOCAL_SECRET)
    .update(`closed:${slug}:${attemptId}`)
    .digest("base64url");
}

export function closedCookieValue(slug: string, attemptId: number): string {
  const id = String(attemptId);
  return `${id}.${mac(slug, id)}`;
}

export function verifyClosedCookie(slug: string, value: string | undefined): boolean {
  const match = VALUE.exec(value ?? "");
  if (!match) return false;
  const expected = Buffer.from(mac(slug, match[1]));
  const given = Buffer.from(match[2]);
  return expected.length === given.length && timingSafeEqual(expected, given);
}
