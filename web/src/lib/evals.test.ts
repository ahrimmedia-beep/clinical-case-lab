import { describe, expect, it } from "vitest";
import report from "@/data/eval-report.json";
import { bestModel, compareModels, displayModel, headline, honestyNotes, parseEvalReport, type EvalReport } from "./evals";

function committed(): EvalReport {
  const loaded = parseEvalReport(report);
  if (!loaded.ok) throw new Error(loaded.issues.join("; "));
  return loaded.report;
}

describe("eval report", () => {
  it("parses the committed report (CI fails here if the backend's shape drifts)", () => {
    expect(parseEvalReport(report).ok).toBe(true);
  });

  it("names the field that breaks the contract", () => {
    const broken = JSON.parse(JSON.stringify(report)) as { models: Record<string, unknown>[] };
    delete broken.models[0].macro_f1;
    const loaded = parseEvalReport(broken);
    expect(loaded.ok).toBe(false);
    if (!loaded.ok) expect(loaded.issues[0]).toMatch(/^models\.0\.macro_f1:/);
  });

  it("accepts the backend's report shape without the sample flag", () => {
    const real = { ...JSON.parse(JSON.stringify(report)), sample: undefined };
    delete real.sample;
    const loaded = parseEvalReport(real);
    expect(loaded.ok).toBe(true);
    if (loaded.ok) expect(headline(loaded.report)?.sample).toBe(false);
  });

  it("picks the best model by macro-F1, ties going to the cheaper one", () => {
    const base = committed();
    const row = (model: string, f1: number, cost: number) => ({ ...base.models[0], model, macro_f1: f1, cost_usd_per_case: cost });
    const tied: EvalReport = { ...base, models: [row("a", 0.9, 0.02), row("b", 0.9, 0.01), row("c", 0.8, 0.001)] };
    expect(bestModel(tied)?.model).toBe("b");
    expect(bestModel({ ...base, models: [] })).toBeNull();
  });

  it("keeps the fake-provider self-check out of the ranking and labels it", () => {
    const base = committed();
    const fake = { ...base.models[0], provider: "fake", model: "fake-gold", macro_f1: 1 };
    const withFake: EvalReport = { ...base, models: [...base.models, fake] };
    expect(bestModel(withFake)?.provider).not.toBe("fake");
    const onlyFake: EvalReport = { ...base, models: [fake] };
    expect(bestModel(onlyFake)).toBeNull();
    expect(headline(onlyFake)).toBeNull();
    expect(displayModel({ provider: "fake", model: "fake-gold" })).toBe("Self-check (fake provider)");
    expect(displayModel({ provider: "claude", model: "claude-sonnet-5" })).toBe("Claude Sonnet 5");
  });

  it("formats the landing headline from the best model", () => {
    expect(headline(committed())).toMatchObject({
      model: "Claude Opus 5.5",
      macroF1: "0.97",
      grounded: "99%",
      hallucination: "0.6%",
      cost: "$0.048",
      models: 4,
      sample: true,
    });
  });

  it("drops the self-check note when the report has no self-check rows", () => {
    const base = committed();
    const fakeNote = "Rows with provider `fake` are a harness self-check (damaged gold labels, no model call), not a model result.";
    const notes = honestyNotes({ ...base, honesty_notes: ["Synthetic gold set.", fakeNote] });
    expect(notes).toEqual(["Synthetic gold set."]);
    const fake = { ...base.models[0], provider: "fake", model: "fake-gold" };
    expect(honestyNotes({ ...base, models: [fake], honesty_notes: [fakeNote] })).toEqual([fakeNote]);
    expect(honestyNotes({ ...base, honesty_notes: undefined }).length).toBeGreaterThanOrEqual(4);
  });
});

describe("production model vs the next one", () => {
  it("compares Opus 4.8 with Opus 5.5 and words the verdict from the numbers", () => {
    const cmp = compareModels(committed(), "claude-opus-4-8", "claude-opus-5-5");
    expect(cmp).not.toBeNull();
    if (!cmp) return;
    expect(cmp.current.model).toBe("claude-opus-4-8");
    expect(cmp.f1Delta).toBeCloseTo(0.0116, 4);
    expect(cmp.costChange).toBeCloseTo(-0.1322, 3);
    expect(cmp.latencyDeltaMs).toBe(1500);
    expect(cmp.verdict).toBe(
      "On this gold set Claude Opus 5.5 is about as accurate (+0.01 macro-F1, within the noise of 8 cases), 13% cheaper per case and 1.5 s slower at the median. Worth a shadow run on your own cases before switching.",
    );
  });

  it("says so plainly when the next model is clearly worse", () => {
    const base = committed();
    const models = base.models.map((m) => (m.model === "claude-opus-5-5" ? { ...m, macro_f1: 0.9, cost_usd_per_case: 0.07, latency_ms_p50: 9000 } : m));
    const cmp = compareModels({ ...base, models }, "claude-opus-4-8", "claude-opus-5-5");
    expect(cmp?.verdict).toBe(
      "On this gold set Claude Opus 5.5 is less accurate (−0.06 macro-F1), 27% more expensive per case and 3.6 s faster at the median. Nothing here argues for switching yet.",
    );
  });

  it("returns null when either model is missing from the run", () => {
    const base = committed();
    expect(compareModels({ ...base, models: base.models.filter((m) => m.model !== "claude-opus-5-5") }, "claude-opus-4-8", "claude-opus-5-5")).toBeNull();
  });
});
