import "server-only";

/** Runtime configuration. Read per call (never at module load) so one image serves every environment. */

function read(name: string): string | null {
  const value = process.env[name]?.trim();
  return value ? value : null;
}

export function apiBaseUrl(): string | null {
  return read("API_BASE_URL")?.replace(/\/+$/, "") ?? null;
}

/** Without API_BASE_URL the API client serves built-in fixtures (UI development, demos without a backend). */
export function isFixtureMode(): boolean {
  return apiBaseUrl() === null;
}

/** Public URL of the API for the "API docs" link. API_BASE_URL may be a private hostname (compose: http://api:8080). */
export function apiDocsUrl(): string | null {
  const base = read("API_PUBLIC_URL")?.replace(/\/+$/, "");
  return base ? `${base}/docs` : null;
}

export function internalApiKey(): string | null {
  return read("INTERNAL_API_KEY");
}
