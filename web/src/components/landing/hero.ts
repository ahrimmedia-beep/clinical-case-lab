/** Which case leads the landing. The LAM case is the rare-disease hero; the API already lists it first among approved cases. */

type Summary = { slug: string; review_status: "draft" | "approved" };

/** Slug prefix of the seeded LAM case ("A second collapsed lung in a young non-smoker" + hash). */
export const HERO_SLUG_PREFIX = "a-second-collapsed-lung";

export function pickHeroCase<T extends Summary>(cases: readonly T[]): { hero: T; isRareDiseaseHero: boolean } | null {
  const lam = cases.find((c) => c.slug.startsWith(HERO_SLUG_PREFIX) && c.review_status === "approved");
  if (lam) return { hero: lam, isRareDiseaseHero: true };
  const approved = cases.find((c) => c.review_status === "approved");
  return approved ? { hero: approved, isRareDiseaseHero: false } : null;
}
