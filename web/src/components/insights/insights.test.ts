import { describe, expect, it } from "vitest";
import { biggestMiss, closedCookieName, keyTestHeadline, lowerFirst, pct, wrongShare } from "./insights";

describe("sponsor view helpers", () => {
  it("formats rates as whole percentages", () => {
    expect(pct(0.836)).toBe("84%");
    expect(pct(null)).toBe("—");
  });

  it("lower-cases the first word inside a sentence but keeps acronyms", () => {
    expect(lowerFirst("Serum VEGF-D")).toBe("serum VEGF-D");
    expect(lowerFirst("HRCT of the chest")).toBe("HRCT of the chest");
    expect(lowerFirst("CT pulmonary angiography")).toBe("CT pulmonary angiography");
  });

  it("picks the key test with the largest accuracy gap (the seeded LAM cohort: HRCT 84% vs 43%)", () => {
    const head = keyTestHeadline([
      { key: "B", text: "Serum VEGF-D", chose_rate: 0.41, dx_accuracy_if_chosen: 0.79, dx_accuracy_if_not: 0.6 },
      { key: "A", text: "High-resolution CT of the chest", chose_rate: 0.62, dx_accuracy_if_chosen: 0.84, dx_accuracy_if_not: 0.43 },
      { key: "D", text: "Full lung function tests", chose_rate: 0.5, dx_accuracy_if_chosen: null, dx_accuracy_if_not: 0.5 },
    ]);
    expect(head).toMatchObject({ key: "A", chosen: "84%", notChosen: "43%", choseRate: "62%" });
    expect(head?.sentence).toBe(
      "Physicians who ordered high-resolution CT of the chest named the right diagnosis 84% of the time; those who skipped it, 43%.",
    );
  });

  it("has no headline when no test helps or there is no data", () => {
    expect(keyTestHeadline([{ key: "A", text: "Spirometry", chose_rate: 0.5, dx_accuracy_if_chosen: 0.4, dx_accuracy_if_not: 0.5 }])).toBeNull();
    expect(keyTestHeadline(undefined)).toBeNull();
  });

  it("finds the correct option the cohort skipped most often", () => {
    const miss = biggestMiss([
      { stage: "interview", label: "Patient interview", missed_correct: [{ key: "B", text: "Hormonal medication?", missed_rate: 0.36 }] },
      { stage: "treatment", label: "Treatment plan", missed_correct: [{ key: "B", text: "Stop the pill", missed_rate: 0.42 }, { key: "A", text: "Anticoagulate", missed_rate: 0.05 }] },
    ]);
    expect(miss).toEqual({ stage: "treatment", label: "Treatment plan", text: "Stop the pill", missedRate: 0.42 });
    expect(biggestMiss([{ stage: "workup", label: "Workup", missed_correct: [] }])).toBeNull();
  });

  it("expresses a wrong diagnosis as a share of all wrong answers", () => {
    expect(wrongShare(14, 212, 0.78)).toBeCloseTo(14 / 47, 5);
    expect(wrongShare(3, 0, 0.5)).toBeNull();
    expect(wrongShare(3, 10, 1)).toBeNull();
  });

  it("names the cookie the player sets on close", () => {
    expect(closedCookieName("a-second-collapsed-lung-1a2b3c")).toBe("closed_a-second-collapsed-lung-1a2b3c");
  });
});
