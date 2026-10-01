import type { ClinicalCase, EvidenceSpan, ExtractResponse, PhiCount } from "@/lib/api/types";
import { formatMs, formatPatient, formatUsd } from "@/lib/format";

export type FactRow = { path: string; group: "Patient" | "Findings" | "Measurements" | "Diagnosis"; label: string; text: string };

/** Paths match EvidenceSpan.path from the pipeline: "findings[3]", "measurements[0]", "final_diagnosis", … */
export function factRows(c: ClinicalCase): FactRow[] {
  const rows: FactRow[] = [
    { path: "patient", group: "Patient", label: "patient", text: formatPatient({ age_years: c.patient.age_years ?? null, sex: c.patient.sex }) },
    { path: "chief_complaint", group: "Patient", label: "complaint", text: c.chief_complaint },
  ];
  (c.findings ?? []).forEach((f, i) => rows.push({ path: `findings[${i}]`, group: "Findings", label: f.category, text: f.text }));
  (c.measurements ?? []).forEach((m, i) => {
    const value = m.value ?? m.value_text ?? "";
    const unit = m.unit ? ` ${m.unit}` : "";
    const flag = m.flag && m.flag !== "normal" ? ` (${m.flag})` : "";
    rows.push({ path: `measurements[${i}]`, group: "Measurements", label: m.kind, text: `${m.name} ${value}${unit}${flag}`.trim() });
  });
  const dx = c.final_diagnosis;
  rows.push({ path: "final_diagnosis", group: "Diagnosis", label: "final", text: dx.icd10 ? `${dx.name} (${dx.icd10})` : dx.name });
  (c.differential ?? []).forEach((d, i) => rows.push({ path: `differential[${i}]`, group: "Diagnosis", label: "differential", text: d.name }));
  return rows;
}

export type Grounding = "grounded" | "ungrounded" | "none";

export function groundingFor(path: string, spans: readonly Pick<EvidenceSpan, "path" | "grounded">[]): Grounding {
  const mine = spans.filter((s) => s.path === path);
  if (mine.length === 0) return "none";
  return mine.some((s) => s.grounded) ? "grounded" : "ungrounded";
}

export function phiSummary(phi: readonly PhiCount[]): string {
  const parts = phi
    .filter((p) => p.count > 0)
    .map((p) => {
      const word = p.label.length <= 3 ? p.label.toUpperCase() : p.label.toLowerCase().replace(/_/g, " ");
      return `${p.count} ${word}${p.count === 1 ? "" : "s"}`;
    });
  return parts.length > 0 ? parts.join(" · ") : "none found";
}

export const DECISION_LABEL: Record<string, string> = {
  interview: "03 · Patient interview",
  differential: "05 · Differential",
  workup: "06 · Workup",
  diagnosis: "08 · Diagnosis",
  treatment: "09 · Treatment plan",
};

// ---------- studio economics strip and step progress ----------

export type Economics = { draftTime: string; cost: string; grounded: number; quoted: number; groundedLabel: string };

/** "Draft in 24 s · $0.02 · 37/38 facts grounded": the cost of a first draft, read off the response. */
export function economics(r: Pick<ExtractResponse, "usage" | "spans">): Economics {
  const ms = r.usage.latency_ms;
  const draftTime = ms >= 10_000 ? `${Math.round(ms / 1000)} s` : formatMs(ms);
  const grounded = r.spans.filter((s) => s.grounded).length;
  return {
    draftTime,
    cost: formatUsd(r.usage.cost_usd),
    grounded,
    quoted: r.spans.length,
    groundedLabel: `${grounded}/${r.spans.length}`,
  };
}

export type StepKey = "deidentify" | "extract" | "ground" | "author" | "validate";
export type StepState = "waiting" | "running" | "done" | "warn";
export type Step = { key: StepKey; label: string; state: StepState; detail: string };

export const STEP_LABELS: Record<StepKey, string> = {
  deidentify: "De-identify",
  extract: "Extract",
  ground: "Ground",
  author: "Author",
  validate: "Validate",
};

const STEP_ORDER: StepKey[] = ["deidentify", "extract", "ground", "author", "validate"];

/**
 * While the request runs the server reports nothing, so the running step is an estimate from elapsed
 * time (two model calls dominate). The last step never completes on its own: only the response does that.
 */
const STEP_STARTS_MS: Record<StepKey, number> = { deidentify: 0, extract: 400, ground: 13_000, author: 14_000, validate: 27_000 };

const RUNNING_HINT: Record<StepKey, string> = {
  deidentify: "masking names, dates and IDs",
  extract: "model call 1: facts with quotes",
  ground: "checking every quote in the text",
  author: "model call 2: decisions and reveals",
  validate: "schema, no-leak and option checks",
};

export function runningSteps(elapsedMs: number): Step[] {
  let current: StepKey = "deidentify";
  for (const key of STEP_ORDER) if (elapsedMs >= STEP_STARTS_MS[key]) current = key;
  const at = STEP_ORDER.indexOf(current);
  return STEP_ORDER.map((key, i) => ({
    key,
    label: STEP_LABELS[key],
    state: i < at ? "done" : i === at ? "running" : "waiting",
    detail: i === at ? RUNNING_HINT[key] : "",
  }));
}

/** What each step produced, read off the finished response. */
export function finishedSteps(r: Pick<ExtractResponse, "phi" | "spans" | "case" | "warnings">): Step[] {
  const masked = r.phi.reduce((n, p) => n + p.count, 0);
  const grounded = r.spans.filter((s) => s.grounded).length;
  const decisions = r.case.decisions.length;
  return [
    { key: "deidentify", label: STEP_LABELS.deidentify, state: "done", detail: masked > 0 ? `${phiSummary(r.phi)} masked` : "no identifiers found" },
    { key: "extract", label: STEP_LABELS.extract, state: "done", detail: `${r.spans.length} facts with quotes` },
    {
      key: "ground",
      label: STEP_LABELS.ground,
      state: grounded === r.spans.length ? "done" : "warn",
      detail: `${grounded}/${r.spans.length} quotes found in the text`,
    },
    { key: "author", label: STEP_LABELS.author, state: "done", detail: `${decisions} decision points` },
    {
      key: "validate",
      label: STEP_LABELS.validate,
      state: r.warnings.length === 0 ? "done" : "warn",
      detail: r.warnings.length === 0 ? "schema valid, nothing to flag" : `${r.warnings.length} ${r.warnings.length === 1 ? "warning" : "warnings"} to check`,
    },
  ];
}
