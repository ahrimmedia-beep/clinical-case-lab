import { describe, expect, it } from "vitest";
import { flaggedItems, hasFailures, reviewSummary } from "./review";

const ok = { status: "ok" as const, items: ["interview: A; B", "diagnosis: PE"] };
const grounding = { status: "warn" as const, items: ["findings[5]: not found", "differential[0]: no quote"] };
const harmful = { status: "warn" as const, items: ["treatment C: Systemic thrombolysis"] };
const noItems = { status: "warn" as const, items: [] };
const leak = { status: "fail" as const, items: ["title names 'pulmonary embolism'"] };

describe("review checklist", () => {
  it("counts the flagged items, not the passing ones", () => {
    expect(flaggedItems([ok, grounding, harmful])).toBe(3);
    expect(flaggedItems([ok, noItems])).toBe(1);
    expect(flaggedItems([ok])).toBe(0);
  });

  it("blocks approval only on a failing check", () => {
    expect(hasFailures([ok, grounding])).toBe(false);
    expect(hasFailures([ok, leak])).toBe(true);
  });

  it("states the reviewer's job in one sentence", () => {
    expect(reviewSummary([ok, grounding, harmful])).toBe(
      "AI-assisted, not AI-generated: the reviewer checks 3 flagged items, not the whole case.",
    );
    expect(reviewSummary([ok, harmful])).toBe("AI-assisted, not AI-generated: the reviewer checks 1 flagged item, not the whole case.");
    expect(reviewSummary([ok])).toMatch(/nothing is flagged/);
  });
});
