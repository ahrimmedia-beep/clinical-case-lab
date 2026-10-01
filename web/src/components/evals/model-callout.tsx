import { MonoTag } from "@/components/ui/mono-tag";
import { perThousandCases, signed, type ModelComparison } from "@/lib/evals";
import { cn } from "@/lib/cn";
import { formatMs, formatRatio, formatScore, formatUsd, modelLabel } from "@/lib/format";

type Row = { label: string; current: string; next: string; change: string; better: boolean | null };

function rows(c: ModelComparison): Row[] {
  const hallDelta = c.next.hallucination_rate - c.current.hallucination_rate;
  const costPct = Math.round(c.costChange * 100);
  return [
    { label: "Macro-F1", current: formatScore(c.current.macro_f1), next: formatScore(c.next.macro_f1), change: signed(c.f1Delta), better: c.f1Delta === 0 ? null : c.f1Delta > 0 },
    {
      label: "Hallucinated",
      current: formatRatio(c.current.hallucination_rate, 1),
      next: formatRatio(c.next.hallucination_rate, 1),
      change: `${signed(hallDelta * 100, 1)} pt`,
      better: hallDelta === 0 ? null : hallDelta < 0,
    },
    {
      label: "Latency p50",
      current: formatMs(c.current.latency_ms_p50),
      next: formatMs(c.next.latency_ms_p50),
      change: `${signed(c.latencyDeltaMs / 1000, 1)} s`,
      better: c.latencyDeltaMs === 0 ? null : c.latencyDeltaMs < 0,
    },
    {
      label: "Cost per case",
      current: formatUsd(c.current.cost_usd_per_case),
      next: formatUsd(c.next.cost_usd_per_case),
      change: `${costPct > 0 ? "+" : costPct < 0 ? "−" : "±"}${Math.abs(costPct)}%`,
      better: costPct === 0 ? null : costPct < 0,
    },
    {
      label: "Per 1,000 cases",
      current: perThousandCases(c.current.cost_usd_per_case),
      next: perThousandCases(c.next.cost_usd_per_case),
      change: "",
      better: null,
    },
  ];
}

/** "Your production model vs. the next one": Opus 4.8 (Eximion's production model per its AI disclosure) against Opus 5.5. */
export function ModelCallout({ comparison, sample }: { comparison: ModelComparison | null; sample: boolean }) {
  return (
    <section
      id="migration"
      aria-labelledby="upgrade-title"
      className="relative overflow-hidden rounded-card border border-line bg-white shadow-card before:absolute before:inset-x-0 before:top-0 before:h-1 before:bg-brand-grad"
    >
      <div className="grid gap-8 p-5 pt-7 sm:p-8 sm:pt-9 lg:grid-cols-[1fr_1.15fr] lg:items-start">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-eyebrow uppercase text-primary-hover">Migration check</span>
            {sample ? <MonoTag tone="clay">Sample figures</MonoTag> : null}
          </div>
          <h2 id="upgrade-title" className="mt-3 text-[clamp(23px,2.6vw,30px)]">
            Your production model vs. the next one
          </h2>
          {comparison ? (
            <>
              <p className="mt-4 text-lead">{comparison.verdict}</p>
              <p className="mt-4 text-[13px] text-muted">
                {modelLabel(comparison.current.model)} is the production model named in Eximion&apos;s public AI disclosure.{" "}
                {modelLabel(comparison.next.model)} always thinks adaptively (effort is the only lever, set to low here), which is where its
                extra latency comes from. Same prompt, same {comparison.next.cases} cases, same scoring.
              </p>
            </>
          ) : (
            <p className="mt-4 text-lead">
              Claude Opus 4.8 and Opus 5.5 are not both in this run yet. The comparison appears once the eval covers both.
            </p>
          )}
        </div>

        {comparison ? (
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Opus comparison (scrolls sideways on small screens)">
            <table className="w-full min-w-[300px] text-left text-[13px] sm:text-[14px]">
              <caption className="sr-only">
                {modelLabel(comparison.current.model)} against {modelLabel(comparison.next.model)}
              </caption>
              <thead>
                <tr className="border-b border-line">
                  <th scope="col" className="py-2 pr-2 sm:pr-3 font-mono text-[10.5px] font-medium uppercase tracking-[.08em] text-muted">
                    <span className="sr-only">Metric</span>
                  </th>
                  <th scope="col" className="px-2 py-2 sm:px-3 text-end align-bottom">
                    <span className="block whitespace-nowrap font-mono text-[10px] font-medium uppercase tracking-[.08em] text-muted">now</span>
                    <span className="whitespace-nowrap text-[13px] font-semibold text-ink">{modelLabel(comparison.current.model).replace("Claude ", "")}</span>
                  </th>
                  <th scope="col" className="px-2 py-2 sm:px-3 text-end align-bottom">
                    <span className="block font-mono text-[10px] font-medium uppercase tracking-[.08em] text-primary-hover">next</span>
                    <span className="whitespace-nowrap text-[13px] font-semibold text-ink">{modelLabel(comparison.next.model).replace("Claude ", "")}</span>
                  </th>
                  <th scope="col" className="py-2 pl-2 sm:pl-3 text-end align-bottom font-mono text-[10.5px] font-medium uppercase tracking-[.08em] text-muted">
                    Change
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows(comparison).map((row) => (
                  <tr key={row.label} data-reveal="fade" className="border-b border-line last:border-0">
                    <th scope="row" className="py-2.5 pr-2 sm:pr-3 text-left text-[13.5px] font-normal text-body">
                      {row.label}
                    </th>
                    <td className="whitespace-nowrap px-2 py-2.5 sm:px-3 text-end tabular-nums text-body">{row.current}</td>
                    <td className="whitespace-nowrap px-2 py-2.5 sm:px-3 text-end font-semibold tabular-nums text-ink">{row.next}</td>
                    <td
                      className={cn(
                        "whitespace-nowrap py-2.5 pl-2 sm:pl-3 text-end font-mono text-[12px] tabular-nums",
                        row.better === true ? "text-primary-hover" : row.better === false ? "text-wrong" : "text-muted",
                      )}
                    >
                      {row.change}
                      {row.better !== null ? <span className="sr-only">{row.better ? " (better)" : " (worse)"}</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </section>
  );
}
