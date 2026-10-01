import { describe, expect, it } from "vitest";
import { pickHeroCase } from "./hero";

const c = (slug: string, review_status: "draft" | "approved" = "approved") => ({ slug, review_status });

describe("pickHeroCase", () => {
  it("leads with the LAM case wherever it sits in the list", () => {
    const picked = pickHeroCase([c("studio-draft-1", "draft"), c("sudden-breathlessness-3f9a1c"), c("a-second-collapsed-lung-in-a-young-non-smoker-9b2e1d")]);
    expect(picked).toEqual({ hero: c("a-second-collapsed-lung-in-a-young-non-smoker-9b2e1d"), isRareDiseaseHero: true });
  });

  it("falls back to the first approved case, never a draft", () => {
    expect(pickHeroCase([c("draft-a", "draft"), c("pe-case"), c("aatd-case")])).toEqual({ hero: c("pe-case"), isRareDiseaseHero: false });
    expect(pickHeroCase([c("a-second-collapsed-lung-draft", "draft")])).toBeNull();
    expect(pickHeroCase([])).toBeNull();
  });
});
