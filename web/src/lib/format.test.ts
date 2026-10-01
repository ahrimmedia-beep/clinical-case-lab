import { describe, expect, it } from "vitest";
import {
  formatInt,
  formatMinutes,
  formatMs,
  formatPatient,
  formatPercentile,
  formatPickRate,
  formatRatio,
  formatScore,
  formatUsd,
  initials,
  modelKey,
  modelLabel,
  ordinalSuffix,
  pluralize,
  stageNo,
} from "./format";

describe("stageNo", () => {
  it("pads stage numbers to two digits", () => {
    expect(stageNo(3)).toBe("03");
    expect(stageNo(12)).toBe("12");
  });
});

describe("percentiles", () => {
  it("uses English ordinal suffixes", () => {
    const shown = [1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 101, 111].map((n) => `${n}${ordinalSuffix(n)}`);
    expect(shown).toEqual(["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "101st", "111th"]);
  });

  it("rounds and clamps the percentile; null stays null", () => {
    expect(formatPercentile(77.6)).toEqual({ value: 78, suffix: "th" });
    expect(formatPercentile(0.4)).toEqual({ value: 0, suffix: "th" });
    expect(formatPercentile(100)).toEqual({ value: 100, suffix: "th" });
    expect(formatPercentile(null)).toBeNull();
  });
});

describe("numbers", () => {
  it("formats ratios, scores and integers", () => {
    expect(formatRatio(0.912)).toBe("91%");
    expect(formatRatio(0.034, 1)).toBe("3.4%");
    expect(formatRatio(null)).toBe("—");
    expect(formatScore(0.9)).toBe("0.90");
    expect(formatScore(undefined)).toBe("—");
    expect(formatInt(12345)).toBe("12,345");
  });

  it("formats money for cheap model calls", () => {
    expect(formatUsd(0)).toBe("$0");
    expect(formatUsd(0.008)).toBe("$0.008");
    expect(formatUsd(0.0214)).toBe("$0.021");
    expect(formatUsd(0.00012)).toBe("$0.00012");
    expect(formatUsd(2.5)).toBe("$2.50");
  });

  it("formats latency", () => {
    expect(formatMs(640)).toBe("640 ms");
    expect(formatMs(1840)).toBe("1.8 s");
    expect(formatMs(23900)).toBe("23.9 s");
  });
});

describe("labels", () => {
  it("describes the patient in plain words", () => {
    expect(formatPatient({ age_years: 34, sex: "female" })).toBe("34-year-old woman");
    expect(formatPatient({ age_years: 67, sex: "male" })).toBe("67-year-old man");
    expect(formatPatient({ age_years: 8, sex: "male" })).toBe("8-year-old boy");
    expect(formatPatient({ age_years: null, sex: "unknown" })).toBe("Patient, age not given");
  });

  it("builds initials without titles", () => {
    expect(initials("Ms. R.")).toBe("R");
    expect(initials("John Smith")).toBe("JS");
    expect(initials(null)).toBe("Pt");
    expect(initials("   ")).toBe("Pt");
  });

  it("pluralizes and formats minutes and pick rates", () => {
    expect(pluralize(1, "attempt")).toBe("1 attempt");
    expect(pluralize(3, "attempt")).toBe("3 attempts");
    expect(pluralize(2, "diagnosis", "diagnoses")).toBe("2 diagnoses");
    expect(formatMinutes(5)).toBe("~5 min");
    expect(formatPickRate(0.42)).toBe("42% of peers chose this");
    expect(formatPickRate(null)).toBeNull();
  });

  it("turns model ids into readable names", () => {
    expect(modelLabel("gemini-3.8-flash")).toBe("Gemini 3.8 Flash");
    expect(modelLabel("claude-sonnet-5-5")).toBe("Claude Sonnet 5.5");
    expect(modelLabel("claude-haiku-4-5@20251001")).toBe("Claude Haiku 4.5");
    expect(modelLabel("gemini-3.5-flash-lite")).toBe("Gemini 3.5 Flash Lite");
    expect(modelKey({ provider: "claude", model: "claude-opus-5-5" })).toBe("claude/claude-opus-5-5");
  });
});
