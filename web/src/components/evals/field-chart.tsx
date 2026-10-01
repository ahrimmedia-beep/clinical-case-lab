import { displayModel, FIELD_LABELS, isSelfCheck, type FieldKey, type ModelRow } from "@/lib/evals";
import { cn } from "@/lib/cn";
import { formatScore, modelKey } from "@/lib/format";

/** Scores below this floor all get the lightest tint: every model clears it, and the eye should go to the gaps above it. */
const FLOOR = 0.75;
const MIN_MIX = 3;
const MAX_MIX = 48; // stays light enough for ink text on every cell (contrast > 7:1)

/** Share of deep teal mixed into white for a score: one hue, light to dark (sequential), clipped at FLOOR. */
export function heatMix(value: number): number {
  const t = Math.min(1, Math.max(0, (value - FLOOR) / (1 - FLOOR)));
  return Math.round(MIN_MIX + t * (MAX_MIX - MIN_MIX));
}

const GROUPS: { title: string; fields: FieldKey[] }[] = [
  { title: "Patient", fields: ["patient_age", "patient_sex"] },
  { title: "Presentation", fields: ["chief_complaint", "final_diagnosis"] },
  { title: "Findings", fields: ["findings_precision", "findings_recall", "findings_f1"] },
  { title: "Measurements", fields: ["measurements_precision", "measurements_recall", "measurements_f1"] },
];

/** One chart for the per-field view: a heat table, fields down, models across, every value printed in its cell. */
export function FieldChart({ models }: { models: ModelRow[] }) {
  const real = models.filter((m) => !isSelfCheck(m));
  return (
    <figure className="overflow-hidden rounded-card border border-line bg-white shadow-card">
      <figcaption className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line bg-surface-alt px-5 py-[13px]">
        <span className="text-[14.5px] font-semibold tracking-[-.015em] text-ink">Score per field, per model</span>
        <span className="ml-auto flex items-center gap-2 font-mono text-[10.5px] text-muted">
          <span aria-hidden="true">{formatScore(FLOOR)} or less</span>
          <span
            aria-hidden="true"
            className="h-2 w-24 rounded-bar"
            style={{
              backgroundImage: `linear-gradient(90deg, color-mix(in oklab, var(--color-primary-deep) ${MIN_MIX}%, var(--color-surface)), color-mix(in oklab, var(--color-primary-deep) ${MAX_MIX}%, var(--color-surface)))`,
            }}
          />
          <span aria-hidden="true">1.00</span>
          <span className="sr-only">Darker cells score higher, from {formatScore(FLOOR)} or less up to 1.00.</span>
        </span>
      </figcaption>
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Score per field (scrolls sideways on small screens)">
        <table className="w-full min-w-[540px] border-separate border-spacing-[3px] px-3 py-3 text-[13px]">
          <thead>
            <tr>
              <th scope="col" className="w-[30%] px-2 pb-1 text-left font-mono text-[10.5px] font-medium uppercase tracking-[.08em] text-muted">
                Field
              </th>
              {models.map((m) => (
                <th
                  key={modelKey(m)}
                  scope="col"
                  className={cn("px-2 pb-1 text-center align-bottom text-[12px] font-medium leading-tight", isSelfCheck(m) ? "text-muted" : "text-ink")}
                >
                  {displayModel(m)}
                </th>
              ))}
            </tr>
          </thead>
          {GROUPS.map((group) => (
            <tbody key={group.title}>
              <tr>
                <th colSpan={models.length + 1} scope="colgroup" className="px-2 pb-0.5 pt-3 text-left font-mono text-[10px] font-medium uppercase tracking-[.1em] text-primary-hover">
                  {group.title}
                </th>
              </tr>
              {group.fields.map((field, fi) => {
                const values = real.map((m) => m.fields[field]);
                const top = Math.max(0, ...values);
                const allEqual = values.every((v) => v === top);
                return (
                  <tr key={field} className="animate-rise" style={{ animationDelay: `${fi * 55}ms` }}>
                    <th scope="row" className="px-2 py-1.5 text-left text-[13px] font-normal text-body">
                      {FIELD_LABELS[field].replace(/^(Findings|Measurements) · /, "")}
                    </th>
                    {models.map((m) => {
                      const value = m.fields[field];
                      const selfCheck = isSelfCheck(m);
                      const mix = heatMix(value);
                      const best = !selfCheck && !allEqual && value === top;
                      return (
                        <td
                          key={modelKey(m)}
                          title={`${displayModel(m)} · ${FIELD_LABELS[field]}: ${formatScore(value)}`}
                          className={cn(
                            "rounded-[6px] px-2 py-1.5 text-center tabular-nums",
                            selfCheck ? "bg-surface-alt text-muted" : "text-ink",
                            best && "font-semibold",
                          )}
                          style={selfCheck ? undefined : { backgroundColor: `color-mix(in oklab, var(--color-primary-deep) ${mix}%, var(--color-surface))` }}
                        >
                          {formatScore(value)}
                          {best ? <span className="sr-only"> (best)</span> : null}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          ))}
        </table>
      </div>
    </figure>
  );
}
