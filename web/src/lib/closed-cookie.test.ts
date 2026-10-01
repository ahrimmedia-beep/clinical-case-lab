import { afterEach, describe, expect, it, vi } from "vitest";
import { closedCookieValue, verifyClosedCookie } from "./closed-cookie";

const SLUG = "sudden-breathlessness-after-a-long-flight-7c2646";

afterEach(() => vi.unstubAllEnvs());

describe("closed_<slug> cookie", () => {
  it("is the attempt id plus an HMAC of slug and attempt id, keyed with INTERNAL_API_KEY", () => {
    vi.stubEnv("INTERNAL_API_KEY", "k3y");
    const value = closedCookieValue(SLUG, 626);
    expect(value).toMatch(/^626\.[A-Za-z0-9_-]{43}$/);
    expect(verifyClosedCookie(SLUG, value)).toBe(true);
  });

  it("rejects a hand-made, edited, moved or foreign-key cookie", () => {
    vi.stubEnv("INTERNAL_API_KEY", "k3y");
    const value = closedCookieValue(SLUG, 626);
    const [, mac] = value.split(".");
    expect(verifyClosedCookie(SLUG, "1")).toBe(false); // the old unsigned marker
    expect(verifyClosedCookie(SLUG, undefined)).toBe(false);
    expect(verifyClosedCookie(SLUG, `627.${mac}`)).toBe(false); // another attempt id
    expect(verifyClosedCookie("another-case-1a2b3c", value)).toBe(false); // another case
    expect(verifyClosedCookie(SLUG, `${value}x`)).toBe(false);
    vi.stubEnv("INTERNAL_API_KEY", "rotated");
    expect(verifyClosedCookie(SLUG, value)).toBe(false);
  });
});
