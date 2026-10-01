import { MonoTag } from "@/components/ui/mono-tag";
import { StateIcon } from "@/components/ui/state-icon";
import type { InsightStage } from "@/lib/api/internal";
import { cn } from "@/lib/cn";
import { DECISION_LABEL } from "@/lib/facts";
import { NOTABLE_MISS, pct } from "./insights";

/** One decision point: how often the cohort picked each option. Correct = teal ✓, harmful = clay tag, the rest grey. */
export function DecisionBars({ stage, index }: { stage: InsightStage; index: number }) {
  const options = stage.options ?? [];
  const missed = new Map((stage.missed_correct ?? []).map((m) => [m.key, m.missed_rate]));
  const correct = options.filter((o) => o.is_correct).length;

  return (
    <section
      aria-labelledby={`stage-${stage.stage}`}
      className="animate-rise overflow-hidden rounded-card border border-line bg-white shadow-card"
      style={{ animationDelay: `${index * 55}ms` }}
    >
      <header className="flex flex-wrap items-center gap-2.5 border-b border-line bg-surface-alt px-5 py-[13px]">
        <h3 id={`stage-${stage.stage}`} className="font-mono text-[11px] font-medium uppercase tracking-[.1em] text-primary-hover">
          {DECISION_LABEL[stage.stage] ?? stage.label}
        </h3>
        <span className="ml-auto font-mono text-[10.5px] text-muted">
          {correct} correct of {options.length}
        </span>
      </header>
      <ul className="space-y-3.5 px-5 py-4">
        {options.map((o, i) => {
          const miss = missed.get(o.key);
          const notable = miss !== undefined && miss >= NOTABLE_MISS;
          return (
            <li key={o.key}>
              <div className="flex items-start gap-2.5">
                {o.is_correct ? (
                  <StateIcon state="right" label="Correct option" className="mt-0.5" />
                ) : (
                  <StateIcon state="neutral" label={o.is_harmful ? "Harmful option" : "Not a correct option"} className="mt-0.5" />
                )}
                <p className="min-w-0 flex-1 text-[13.5px] leading-snug text-ink [overflow-wrap:anywhere]">
                  <span className="mr-1.5 font-mono text-[11px] text-muted">{o.key}</span>
                  {o.text}
                  {o.is_harmful ? (
                    <MonoTag tone="clay" className="ml-2 align-middle">
                      harmful
                    </MonoTag>
                  ) : null}
                </p>
                <span className="flex-none text-[14px] font-semibold tabular-nums text-ink">{pct(o.pick_rate)}</span>
              </div>
              <span className="ml-[29px] mt-1.5 block h-[7px] overflow-hidden rounded-bar bg-surface-alt" aria-hidden="true">
                <span
                  className={cn(
                    "block h-full origin-left animate-grow-x rounded-bar",
                    o.is_harmful ? "bg-wrong" : o.is_correct ? "bg-primary" : "bg-line-strong",
                  )}
                  style={{ width: `${Math.max(0, Math.min(100, o.pick_rate * 100))}%`, animationDelay: `${index * 55 + i * 40}ms` }}
                />
              </span>
              {miss !== undefined && miss > 0 ? (
                <p
                  className={cn(
                    "ml-[29px] mt-1.5 inline-block font-mono text-[11px]",
                    notable ? "rounded-[5px] border border-missed-border bg-missed-tint px-1.5 py-0.5 text-missed-text" : "text-muted",
                  )}
                >
                  missed by {pct(miss)}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
