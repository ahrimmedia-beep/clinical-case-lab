/** Pure helpers for the sponsor view (★3). Inputs mirror CaseInsights from the generated schema. */

type KeyTest = { key: string; text: string; chose_rate: number; dx_accuracy_if_chosen?: number | null; dx_accuracy_if_not?: number | null };
type Missed = { key: string; text: string; missed_rate: number };
type StageLike = { stage: string; label: string; missed_correct?: Missed[] };

/** Misses at or above this share get the amber callout; below it they are listed quietly. */
export const NOTABLE_MISS = 0.25;

export function pct(r: number | null | undefined): string {
  if (r === null || r === undefined || Number.isNaN(r)) return "—";
  return `${Math.round(r * 100)}%`;
}

/** "High-resolution CT" stays, "Serum VEGF-D" → "serum VEGF-D": sentence case inside a sentence, acronyms kept. */
export function lowerFirst(text: string): string {
  if (text.length < 2 || text[1] !== text[1].toLowerCase()) return text;
  return text[0].toLowerCase() + text.slice(1);
}

export type KeyTestHeadline = { key: string; test: string; chosen: string; notChosen: string; choseRate: string; gap: number; sentence: string };

/** The key test with the largest accuracy gap between those who ordered it and those who did not. */
export function keyTestHeadline(tests: readonly KeyTest[] | undefined): KeyTestHeadline | null {
  const scored = (tests ?? [])
    .filter((t) => typeof t.dx_accuracy_if_chosen === "number" && typeof t.dx_accuracy_if_not === "number")
    .map((t) => ({ t, gap: (t.dx_accuracy_if_chosen as number) - (t.dx_accuracy_if_not as number) }))
    .sort((a, b) => b.gap - a.gap);
  const best = scored[0];
  if (!best || best.gap <= 0) return null;
  const { t, gap } = best;
  const chosen = pct(t.dx_accuracy_if_chosen);
  const notChosen = pct(t.dx_accuracy_if_not);
  return {
    key: t.key,
    test: t.text,
    chosen,
    notChosen,
    choseRate: pct(t.chose_rate),
    gap,
    sentence: `Physicians who ordered ${lowerFirst(t.text)} named the right diagnosis ${chosen} of the time; those who skipped it, ${notChosen}.`,
  };
}

export type BiggestMiss = { stage: string; label: string; text: string; missedRate: number };

/** The correct option the cohort skipped most often, across every decision point. */
export function biggestMiss(stages: readonly StageLike[] | undefined): BiggestMiss | null {
  let best: BiggestMiss | null = null;
  for (const s of stages ?? []) {
    for (const m of s.missed_correct ?? []) {
      if (!best || m.missed_rate > best.missedRate) best = { stage: s.stage, label: s.label, text: m.text, missedRate: m.missed_rate };
    }
  }
  return best && best.missedRate > 0 ? best : null;
}

/** Share of all wrong diagnoses this one accounts for, given the cohort and its accuracy. */
export function wrongShare(count: number, cohortSize: number, accuracy: number | null | undefined): number | null {
  if (accuracy === null || accuracy === undefined || cohortSize <= 0) return null;
  const wrong = Math.round(cohortSize * (1 - accuracy));
  return wrong > 0 ? Math.min(1, count / wrong) : null;
}

/** The httpOnly cookie C1's submitAttempt sets when this browser closes the case. */
export function closedCookieName(slug: string): string {
  return `closed_${slug}`;
}
