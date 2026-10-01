import { displayModel, isSelfCheck, type ModelRow } from "@/lib/evals";
import { cn } from "@/lib/cn";
import { formatInt, formatMs, formatRatio, formatScore, formatUsd, modelKey } from "@/lib/format";

const HEAD = ["Model", "Macro-F1", "Diagnosis", "Schema valid", "Quotes found", "Hallucinated", "Negations", "Latency p50 / p95", "Cost / case"];
const CELL = "px-3 py-3 align-top tabular-nums";

type Props = { models: ModelRow[]; bestKey: string | null; productionModel: string };

export function ModelTable({ models, bestKey, productionModel }: Props) {
  return (
    <div className="overflow-hidden rounded-card border border-line bg-white shadow-card">
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Model comparison (scrolls sideways on small screens)">
        <table className="w-full min-w-[1000px] text-left text-[13.5px]">
          <caption className="sr-only">Extraction quality, speed and cost per model on the gold set</caption>
          <thead className="border-b border-line bg-surface-alt">
            <tr>
              {HEAD.map((h) => (
                <th key={h} scope="col" className="whitespace-nowrap px-3 py-3 font-mono text-[10.5px] first:px-4 font-medium uppercase tracking-[.08em] text-muted">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {models.map((m, i) => {
              const key = modelKey(m);
              return (
                <tr
                  key={key}
                  className={cn("animate-rise border-t border-line first:border-0", isSelfCheck(m) && "bg-surface-alt text-muted opacity-70")}
                  style={{ animationDelay: `${i * 55}ms` }}
                >
                  <th scope="row" className="min-w-[200px] px-4 py-3 text-left align-top font-normal">
                    <span className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium text-ink">{displayModel(m)}</span>
                      {m.model === productionModel ? (
                        <span className="rounded-full border border-line-strong px-1.5 py-0.5 font-mono text-[9.5px] uppercase tracking-[.08em] text-muted">
                          in production
                        </span>
                      ) : null}
                    </span>
                    <span className="block whitespace-nowrap font-mono text-[10.5px] text-muted">
                      {m.provider} · {m.model}
                    </span>
                  </th>
                  <td className={CELL}>
                    <span className="inline-flex items-center gap-1.5 font-semibold text-ink">
                      {formatScore(m.macro_f1)}
                      {key === bestKey ? (
                        <span className="rounded-full bg-primary-tint px-1.5 py-0.5 font-mono text-[9.5px] font-medium uppercase tracking-[.08em] text-primary-hover">
                          best
                        </span>
                      ) : null}
                    </span>
                  </td>
                  <td className={CELL}>
                    {formatRatio(m.fields.final_diagnosis)}
                    <span className="block font-mono text-[10.5px] text-muted">of {m.cases} cases</span>
                  </td>
                  <td className={CELL}>
                    {formatRatio(m.schema_valid_first_try_rate)} first try
                    <span className="block whitespace-nowrap font-mono text-[10.5px] text-muted">{formatRatio(m.schema_valid_rate)} after repair</span>
                  </td>
                  <td className={CELL}>{formatRatio(m.grounded_ratio)}</td>
                  <td className={CELL}>{formatRatio(m.hallucination_rate, 1)}</td>
                  <td className={CELL}>{m.negation_errors}</td>
                  <td className={CELL}>
                    {formatMs(m.latency_ms_p50)} / {formatMs(m.latency_ms_p95)}
                  </td>
                  <td className={CELL}>
                    {formatUsd(m.cost_usd_per_case)}
                    <span className="block whitespace-nowrap font-mono text-[10.5px] text-muted">
                      {formatInt(m.tokens_in_avg)} in · {formatInt(m.tokens_out_avg)} out
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
