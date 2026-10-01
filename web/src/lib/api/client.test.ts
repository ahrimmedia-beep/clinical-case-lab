import { afterEach, describe, expect, it, vi } from "vitest";
import { extractCase, getCase, listCases } from "./client";
import { extractResponse, peCasePublic } from "./fixtures";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("fixture mode", () => {
  it("serves the built-in cases when API_BASE_URL is unset", async () => {
    vi.stubEnv("API_BASE_URL", "");
    expect((await listCases()).map((c) => c.slug)).toEqual([
      peCasePublic.slug,
      "recurrent-pneumothorax-after-exertion-ai-draft",
      "layout-stress-test",
    ]);
    expect(await getCase(peCasePublic.slug)).toEqual(peCasePublic);
    expect(await getCase("no-such-case")).toBeNull();
  });

  it("returns an extraction whose spans point into the source text", async () => {
    vi.stubEnv("API_BASE_URL", "");
    const res = await extractCase({ text: "x".repeat(60), provider: "gemini", model: null });
    expect(res).toBe(extractResponse);
    for (const s of res.spans.filter((x) => x.grounded)) {
      expect(res.source_text.slice(s.start ?? 0, s.end ?? 0)).toBe(s.quote);
    }
    expect(res.spans.filter((x) => !x.grounded).map((x) => x.path)).toEqual(["findings[5]"]);
  });
});

describe("API down", () => {
  it("turns a refused connection into ApiError 503", async () => {
    vi.stubEnv("API_BASE_URL", "http://127.0.0.1:9");
    await expect(listCases()).rejects.toMatchObject({ name: "ApiError", status: 503 });
  });
});
