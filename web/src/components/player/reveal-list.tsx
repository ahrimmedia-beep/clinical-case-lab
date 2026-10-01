"use client";

import type { PublicOption, RevealOut, Stage } from "@/lib/api/types";

type Props = { stageKey: Stage; options: PublicOption[]; reveals: RevealOut[] | undefined; pending: boolean; error: string | null };

/** What the patient said / what the tests showed, for the options you chose. Carries no correctness. */
export function RevealList({ stageKey, options, reveals, pending, error }: Props) {
  const label = stageKey === "interview" ? "Answer" : "Result";
  if (!reveals) {
    if (error) return <p role="alert" className="mt-4 font-mono text-[12px] text-error">{error}</p>;
    return pending ? <p className="mt-4 font-mono text-[12px] text-muted">{stageKey === "interview" ? "Asking…" : "Waiting for results…"}</p> : null;
  }
  if (reveals.length === 0) return <p className="mt-4 text-[14px] text-muted">Nothing further to report.</p>;
  return (
    <ul className="mt-4 space-y-2" aria-label={stageKey === "interview" ? "What the patient told you" : "What came back"}>
      {reveals.map((r) => (
        <li key={r.key} className="animate-rise rounded-tile border border-line bg-surface-alt px-4 py-3">
          <p className="text-[12.5px] text-muted [overflow-wrap:anywhere]">{options.find((o) => o.key === r.key)?.text ?? r.key}</p>
          <p className="mt-1 text-[14.5px] text-ink [overflow-wrap:anywhere]">
            <span className="mr-2 font-mono text-[10px] uppercase tracking-[.08em] text-primary-hover">{label}</span>
            {r.reveal}
          </p>
        </li>
      ))}
    </ul>
  );
}
