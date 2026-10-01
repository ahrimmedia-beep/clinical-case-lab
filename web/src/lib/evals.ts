import { z } from "zod";
import raw from "@/data/eval-report.json";
import { formatRatio, formatScore, formatUsd, modelLabel } from "@/lib/format";

/**
 * Mirrors backend/evals/reports/latest.json (`evals/report.py`, `EvalReport`). The deploy step copies
 * that file to src/data/eval-report.json; `sample` exists only in the placeholder committed before the
 * live run, so the "sample figures" label disappears by itself.
 */

const ratio = z.number().min(0).max(1);

const fieldsSchema = z.object({
  patient_age: ratio,
  patient_sex: ratio,
  chief_complaint: ratio,
  final_diagnosis: ratio,
  findings_precision: ratio,
  findings_recall: ratio,
  findings_f1: ratio,
  measurements_precision: ratio,
  measurements_recall: ratio,
  measurements_f1: ratio,
});

const modelSchema = z.object({
  provider: z.string(),
  model: z.string(),
  cases: z.number().int().nonnegative(),
  schema_valid_rate: ratio,
  schema_valid_first_try_rate: ratio,
  macro_f1: ratio,
  fields: fieldsSchema,
  grounded_ratio: ratio,
  hallucination_rate: ratio,
  negation_errors: z.number().int().nonnegative(),
  latency_ms_p50: z.number().nonnegative(),
  latency_ms_p95: z.number().nonnegative(),
  cost_usd_per_case: z.number().nonnegative(),
  tokens_in_avg: z.number().nonnegative(),
  tokens_out_avg: z.number().nonnegative(),
});

const perCaseSchema = z.object({
  case_id: z.string(),
  provider: z.string(),
  model: z.string(),
  findings_f1: ratio,
  measurements_f1: ratio,
  diagnosis_correct: z.boolean(),
  grounded_ratio: ratio,
  latency_ms: z.number().nonnegative(),
  cost_usd: z.number().nonnegative(),
  notes: z.array(z.string()),
});

export const evalReportSchema = z.object({
  sample: z.boolean().optional(),
  generated_at: z.string(),
  prompt_version: z.string(),
  split: z.string(),
  gold_cases: z.number().int().nonnegative(),
  models: z.array(modelSchema),
  per_case: z.array(perCaseSchema),
  honesty_notes: z.array(z.string()).optional(),
});

export type EvalReport = z.infer<typeof evalReportSchema>;
export type ModelRow = EvalReport["models"][number];
export type FieldKey = keyof ModelRow["fields"];

export const FIELD_LABELS: Record<FieldKey, string> = {
  patient_age: "Patient age",
  patient_sex: "Patient sex",
  chief_complaint: "Chief complaint",
  final_diagnosis: "Final diagnosis",
  findings_precision: "Findings · precision",
  findings_recall: "Findings · recall",
  findings_f1: "Findings · F1",
  measurements_precision: "Measurements · precision",
  measurements_recall: "Measurements · recall",
  measurements_f1: "Measurements · F1",
};

export type LoadedReport = { ok: true; report: EvalReport } | { ok: false; issues: string[] };

export function parseEvalReport(input: unknown): LoadedReport {
  const parsed = evalReportSchema.safeParse(input);
  if (parsed.success) return { ok: true, report: parsed.data };
  return {
    ok: false,
    issues: parsed.error.issues.slice(0, 6).map((issue) => `${issue.path.map(String).join(".") || "(root)"}: ${issue.message}`),
  };
}

export function loadEvalReport(): LoadedReport {
  return parseEvalReport(raw);
}

/** The backend's deterministic fake provider: proves the harness scores correctly, says nothing about real models. */
export function isSelfCheck(m: { provider: string }): boolean {
  return m.provider === "fake";
}

export function displayModel(m: { provider: string; model: string }): string {
  return isSelfCheck(m) ? "Self-check (fake provider)" : modelLabel(m.model);
}

export function bestModel(report: EvalReport): ModelRow | null {
  const real = report.models.filter((m) => !isSelfCheck(m));
  if (real.length === 0) return null;
  return [...real].sort((a, b) => b.macro_f1 - a.macro_f1 || a.cost_usd_per_case - b.cost_usd_per_case)[0];
}

export type Headline = { model: string; macroF1: string; grounded: string; hallucination: string; cost: string; models: number; sample: boolean };

export function headline(report: EvalReport): Headline | null {
  const best = bestModel(report);
  if (!best) return null;
  return {
    model: modelLabel(best.model),
    macroF1: formatScore(best.macro_f1),
    grounded: formatRatio(best.grounded_ratio),
    hallucination: formatRatio(best.hallucination_rate, 1),
    cost: formatUsd(best.cost_usd_per_case),
    models: report.models.filter((m) => !isSelfCheck(m)).length,
    sample: report.sample === true,
  };
}

/** Spec §11: shown on the page whatever the report carries, so an old report cannot drop them. */
const DEFAULT_HONESTY_NOTES = [
  "The gold set is synthetic: 8 pulmonology case reports written for this repository; no real patient is described.",
  "Labels were drafted with an LLM before each text was written, then checked by hand.",
  "8 cases is a smoke-level harness: it catches regressions and large gaps between models; it is not a benchmark.",
  "Claude helped draft the labels and is also evaluated: a known bias in its favour.",
];

export function honestyNotes(report: EvalReport): string[] {
  const notes = report.honesty_notes && report.honesty_notes.length > 0 ? report.honesty_notes : DEFAULT_HONESTY_NOTES;
  const hasSelfCheck = report.models.some(isSelfCheck);
  return notes.filter((note) => hasSelfCheck || !note.includes("`fake`"));
}

// ---------- "your production model vs. the next one" ----------

/** With eight cases, macro-F1 gaps below this are noise, and the verdict says so. */
const F1_NOISE = 0.02;

export type ModelComparison = {
  current: ModelRow;
  next: ModelRow;
  /** next − current */
  f1Delta: number;
  /** relative change in cost per case, e.g. −0.13 = 13 % cheaper */
  costChange: number;
  /** next − current, p50 */
  latencyDeltaMs: number;
  verdict: string;
};

export function signed(value: number, digits = 2): string {
  const rounded = Number(value.toFixed(digits));
  return `${rounded < 0 ? "−" : "+"}${Math.abs(rounded).toFixed(digits)}`;
}

export function compareModels(report: EvalReport, currentModel: string, nextModel: string): ModelComparison | null {
  const current = report.models.find((m) => m.model === currentModel && !isSelfCheck(m));
  const next = report.models.find((m) => m.model === nextModel && !isSelfCheck(m));
  if (!current || !next) return null;

  const f1Delta = next.macro_f1 - current.macro_f1;
  const costChange = current.cost_usd_per_case > 0 ? (next.cost_usd_per_case - current.cost_usd_per_case) / current.cost_usd_per_case : 0;
  const latencyDeltaMs = next.latency_ms_p50 - current.latency_ms_p50;
  const cases = Math.min(current.cases, next.cases);

  const accuracy =
    Math.abs(f1Delta) < F1_NOISE
      ? `about as accurate (${signed(f1Delta)} macro-F1, within the noise of ${cases} cases)`
      : `${f1Delta > 0 ? "more" : "less"} accurate (${signed(f1Delta)} macro-F1)`;
  const pct = Math.round(Math.abs(costChange) * 100);
  const cost = pct === 0 ? "the same price per case" : `${pct}% ${costChange < 0 ? "cheaper" : "more expensive"} per case`;
  const seconds = (Math.abs(latencyDeltaMs) / 1000).toFixed(1);
  const speed = Math.abs(latencyDeltaMs) < 500 ? "about as fast" : `${seconds} s ${latencyDeltaMs > 0 ? "slower" : "faster"} at the median`;

  const advice =
    f1Delta > -F1_NOISE && costChange < 0
      ? "Worth a shadow run on your own cases before switching."
      : f1Delta >= F1_NOISE
        ? "Worth a shadow run if the accuracy gain justifies the cost."
        : "Nothing here argues for switching yet.";

  return {
    current,
    next,
    f1Delta,
    costChange,
    latencyDeltaMs,
    verdict: `On this gold set ${modelLabel(next.model)} is ${accuracy}, ${cost} and ${speed}. ${advice}`,
  };
}

/** "$55" for 1,000 cases: the unit a content team budgets in. */
export function perThousandCases(costPerCase: number): string {
  return `$${Math.round(costPerCase * 1000).toLocaleString("en-US")}`;
}
