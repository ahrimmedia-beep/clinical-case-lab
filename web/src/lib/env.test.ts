import { afterEach, describe, expect, it, vi } from "vitest";
import { apiBaseUrl, apiDocsUrl, internalApiKey, isFixtureMode } from "./env";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("runtime env", () => {
  it("is in fixture mode when API_BASE_URL is empty or blank", () => {
    vi.stubEnv("API_BASE_URL", "");
    expect(isFixtureMode()).toBe(true);
    vi.stubEnv("API_BASE_URL", "   ");
    expect(apiBaseUrl()).toBeNull();
  });

  it("strips trailing slashes so paths join cleanly", () => {
    vi.stubEnv("API_BASE_URL", "https://api.example.run.app///");
    expect(apiBaseUrl()).toBe("https://api.example.run.app");
    expect(isFixtureMode()).toBe(false);
  });

  it("builds the public docs link only from API_PUBLIC_URL", () => {
    vi.stubEnv("API_BASE_URL", "http://api:8080");
    vi.stubEnv("API_PUBLIC_URL", "");
    expect(apiDocsUrl()).toBeNull();
    vi.stubEnv("API_PUBLIC_URL", "https://api.example.run.app/");
    expect(apiDocsUrl()).toBe("https://api.example.run.app/docs");
  });

  it("treats a blank internal key as missing", () => {
    vi.stubEnv("INTERNAL_API_KEY", " ");
    expect(internalApiKey()).toBeNull();
    vi.stubEnv("INTERNAL_API_KEY", "k-123");
    expect(internalApiKey()).toBe("k-123");
  });
});
