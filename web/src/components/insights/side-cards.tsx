import { Card, CardHeader } from "@/components/ui/card";
import { StateIcon } from "@/components/ui/state-icon";
import type { Benchmark } from "@/lib/api/types";
import type { WrongDiagnosis } from "@/lib/api/internal";
import { modelLabel } from "@/lib/format";
import { pct, wrongShare } from "./insights";

/** The most common wrong calls, grouped the way the scorer normalizes them. */
export function WrongDiagnoses({ items, cohortSize, accuracy }: { items: WrongDiagnosis[]; cohortSize: number; accuracy: number | null }) {
  const top = Math.max(1, ...items.map((w) => w.count));
  return (
    <Card>
      <CardHeader title="Most common wrong calls" tag={`top ${items.length}`} />
      {items.length === 0 ? (
        <p className="px-5 py-4 text-[14px] text-muted">No wrong diagnoses recorded yet.</p>
      ) : (
        <ol className="space-y-3 px-5 py-4">
          {items.map((w, i) => {
            const share = wrongShare(w.count, cohortSize, accuracy);
            return (
              <li key={w.text}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="min-w-0 text-[13.5px] text-ink [overflow-wrap:anywhere]">{w.text}</span>
                  <span className="flex-none font-mono text-[11.5px] tabular-nums text-muted">
                    {w.count}
                    {share !== null ? ` · ${pct(share)} of wrong calls` : ""}
                  </span>
                </div>
                <span className="mt-1.5 block h-[5px] overflow-hidden rounded-bar bg-surface-alt" aria-hidden="true">
                  <span
                    className="block h-full origin-left animate-grow-x rounded-bar bg-line-strong"
                    style={{ width: `${(w.count / top) * 100}%`, animationDelay: `${i * 40}ms` }}
                  />
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}

/** AI players (★1) on the same case: shown next to the cohort, never inside it. */
export function AiBenchmarks({ items }: { items: Benchmark[] }) {
  return (
    <Card>
      <CardHeader title="AI players on this case" tag="blinded, same scoring" />
      {items.length === 0 ? (
        <p className="px-5 py-4 text-[14px] text-muted">No AI player has played this case yet.</p>
      ) : (
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="AI players (scrolls sideways on small screens)">
          <table className="w-full min-w-[360px] text-left text-[13.5px]">
            <thead>
              <tr className="border-b border-line">
                {["Model", "Points", "Diagnosis", "Confidence"].map((h) => (
                  <th key={h} scope="col" className="px-5 py-2.5 font-mono text-[10.5px] font-medium uppercase tracking-[.08em] text-muted first:pl-5">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map((b) => (
                <tr key={b.model} className="border-b border-line last:border-0">
                  <th scope="row" className="px-5 py-2.5 text-left font-medium text-ink">
                    {/* The API's label is the stored "ai:<model>" tag; show the model's own name. */}
                    {b.model ? modelLabel(b.model) : b.label}
                  </th>
                  <td className="px-5 py-2.5 tabular-nums">
                    {b.points}/{b.max_points}
                  </td>
                  <td className="px-5 py-2.5">
                    <StateIcon state={b.diagnosis_correct ? "right" : "wrong"} label={b.diagnosis_correct ? "Right diagnosis" : "Wrong diagnosis"} />
                  </td>
                  <td className="whitespace-nowrap px-5 py-2.5 text-body">
                    {b.confidence}/5 <span className="font-mono text-[11px] text-muted">{b.calibration}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="border-t border-line px-5 py-3 text-[12.5px] text-muted">
        Each model played blinded, saw only what a physician sees, and was scored by the same code. They are kept out of every cohort figure on
        this page.
      </p>
    </Card>
  );
}
