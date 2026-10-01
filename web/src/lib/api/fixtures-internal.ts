import "server-only";
import { draftCasePublic, extractResponse, findCase, peAttemptResult, peCasePublic } from "./fixtures";
import type { ApproveOutcome, CaseInsights, CaseReview, InsightStage, ReviewChecklistItem } from "./internal";
import type { CaseCreated, ClinicalCase } from "./types";

/*
 * Fixture mode for the internal-key endpoints. The draft fixture reuses the studio's extracted PE
 * case (so "Publish as draft" in fixture mode lands on a review of the case just extracted); the
 * checklist is computed the way backend/app/repository/review.py does it, from the same data.
 */

const DRAFT = extractResponse.case;
const SOURCE = extractResponse.source_text;

function check(id: string, label: string, status: ReviewChecklistItem["status"], detail: string, items: string[] = []): ReviewChecklistItem {
  return { id, label, status, detail, items };
}

function groundingCheck(c: ClinicalCase): ReviewChecklistItem {
  const facts: [string, string, string | null | undefined][] = [
    ...(c.findings ?? []).map((f, i): [string, string, string | null | undefined] => [`findings[${i}]`, f.text, f.evidence]),
    ...(c.measurements ?? []).map((m, i): [string, string, string | null | undefined] => [`measurements[${i}]`, m.name, m.evidence]),
    ["final_diagnosis", c.final_diagnosis.name, c.final_diagnosis.evidence],
    ...(c.differential ?? []).map((d, i): [string, string, string | null | undefined] => [`differential[${i}]`, d.name, d.evidence]),
  ];
  const flagged = facts.flatMap(([path, what, evidence]) => {
    const quote = (evidence ?? "").trim();
    if (!quote) return [`${path} "${what}": no evidence quote`];
    return SOURCE.toLowerCase().includes(quote.toLowerCase()) ? [] : [`${path} "${what}": evidence not found in the source text`];
  });
  const label = "Evidence grounded in the source text";
  if (flagged.length === 0) return check("grounding", label, "ok", `All ${facts.length} facts quote the source verbatim.`);
  return check("grounding", label, "warn", `${flagged.length} of ${facts.length} facts are not backed by a verbatim quote.`, flagged);
}

function harmfulCheck(c: ClinicalCase): ReviewChecklistItem {
  const flagged = c.decisions.flatMap((d) => (d.options ?? []).filter((o) => o.is_harmful).map((o) => `${d.stage} ${o.key}: ${o.text}`));
  const label = "Harmful options to sign off";
  if (flagged.length === 0) return check("harmful_options", label, "ok", "No option is marked harmful.");
  return check(
    "harmful_options",
    label,
    "warn",
    `${flagged.length} option(s) are marked harmful; picking one zeroes the treatment score. Confirm each is truly harmful.`,
    flagged,
  );
}

function answerKeyCheck(c: ClinicalCase): ReviewChecklistItem {
  const pathway = c.decisions.map((d) =>
    d.stage === "diagnosis"
      ? `diagnosis: ${c.final_diagnosis.name} (also accepted: ${(d.accepted_answers ?? []).filter((a) => a !== c.final_diagnosis.name).join(", ")})`
      : `${d.stage}: ${(d.options ?? [])
          .filter((o) => o.is_correct)
          .map((o) => `${o.key} ${o.text}`)
          .join("; ")}`,
  );
  return check(
    "answer_key",
    "Answer key: confirm the pathway",
    "ok",
    `${pathway.length} decision stages; confirm the correct options form the right pathway.`,
    pathway,
  );
}

function buildReview(slug: string, c: ClinicalCase, status: CaseReview["review_status"]): CaseReview {
  const diagnosis = c.decisions.find((d) => d.stage === "diagnosis");
  return {
    slug,
    title: c.title,
    review_status: status,
    source: {
      kind: c.source?.kind ?? "llm",
      provider: c.source?.provider ?? null,
      model: c.source?.model ?? null,
      prompt_version: c.source?.prompt_version ?? null,
    },
    answer_key: {
      final_diagnosis: c.final_diagnosis,
      accepted_answers: diagnosis?.accepted_answers ?? [],
      stages: c.decisions.map((d) => ({
        stage: d.stage,
        prompt: d.prompt,
        explanation: d.explanation,
        options: (d.options ?? []).map((o) => ({
          key: o.key,
          text: o.text,
          is_correct: o.is_correct,
          is_harmful: o.is_harmful,
          feedback: o.feedback ?? null,
          reveal: o.reveal ?? null,
        })),
      })),
    },
    checklist: [
      groundingCheck(c),
      harmfulCheck(c),
      check(
        "no_leak",
        "No answer before the debrief",
        "ok",
        "Title, vignette, prompts and reveals do not name the diagnosis. 1 given-stage item(s) naming the diagnosis are withheld until the debrief.",
      ),
      answerKeyCheck(c),
      check("phi", "No identifiers in the source text", "ok", "No email, phone, SSN, record number or date found."),
    ],
  };
}

export function reviewFor(slug: string): CaseReview | null {
  if (slug === draftCasePublic.slug) return buildReview(slug, DRAFT, "draft");
  const known = findCase(slug);
  return known ? buildReview(slug, { ...DRAFT, title: known.title, source: { kind: "manual" } }, "approved") : null;
}

export function approve(slug: string): ApproveOutcome {
  if (slug === draftCasePublic.slug) {
    return { status: "approved", result: { slug, review_status: "approved", reviewed_at: new Date().toISOString() } };
  }
  return findCase(slug) ? { status: "already_approved" } : { status: "not_found" };
}

/** Fixture publish lands on the draft fixture, so the studio → review flow works without a backend. */
export const draftCreated: CaseCreated = { id: draftCasePublic.id, slug: draftCasePublic.slug, created: true };

// ---------- sponsor insights (the PE case's simulated cohort, numbers consistent with peAttemptResult) ----------

const PICKS: Record<string, Record<string, number>> = {
  interview: { A: 0.81, B: 0.64, C: 0.22 },
  differential: { A: 0.93, B: 0.71, C: 0.12 },
  workup: { A: 0.88, B: 0.74, C: 0.09 },
  treatment: { A: 0.95, B: 0.58, C: 0.07 },
};

function insightStages(): InsightStage[] {
  return peAttemptResult.stages
    .filter((s) => s.key in PICKS)
    .map((s) => {
      const options = (s.options ?? []).map((o) => {
        const correct = o.state === "right" || o.state === "missed";
        return { key: o.key, text: o.text, is_correct: correct, is_harmful: o.is_harmful, pick_rate: PICKS[s.key][o.key] ?? 0 };
      });
      return {
        stage: s.key as InsightStage["stage"],
        label: s.label,
        options,
        missed_correct: options
          .filter((o) => o.is_correct)
          .map((o) => ({ key: o.key, text: o.text, missed_rate: Number((1 - o.pick_rate).toFixed(4)) }))
          .sort((a, b) => b.missed_rate - a.missed_rate),
      };
    });
}

export function insightsFor(slug: string): CaseInsights | null {
  const known = findCase(slug);
  if (!known) return null;
  return {
    slug,
    title: known.title,
    cohort_size: slug === peCasePublic.slug ? 212 : 0,
    cohort_is_simulated: true,
    diagnosis_accuracy: 0.78,
    top_wrong_diagnoses: [
      { text: "Pneumothorax", count: 14 },
      { text: "Community-acquired pneumonia", count: 9 },
      { text: "Pericarditis", count: 6 },
      { text: "Musculoskeletal chest pain", count: 4 },
      { text: "Acute coronary syndrome", count: 3 },
    ],
    stages: insightStages(),
    key_tests: [
      { key: "A", text: "CT pulmonary angiography", chose_rate: 0.88, dx_accuracy_if_chosen: 0.84, dx_accuracy_if_not: 0.31 },
      { key: "B", text: "D-dimer", chose_rate: 0.74, dx_accuracy_if_chosen: 0.8, dx_accuracy_if_not: 0.71 },
    ],
    benchmarks: peAttemptResult.benchmarks ?? [],
  };
}
