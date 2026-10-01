import type { KeyTestEffect } from "@/lib/api/internal";
import { keyTestHeadline, lowerFirst, pct } from "./insights";

function Bar({ label, value, tone }: { label: string; value: number | null | undefined; tone: "primary" | "muted" }) {
  const width = typeof value === "number" ? Math.max(0, Math.min(100, value * 100)) : 0;
  return (
    <div className="grid grid-cols-[minmax(0,118px)_minmax(0,1fr)_44px] items-center gap-3 sm:grid-cols-[150px_minmax(0,1fr)_48px]">
      <span className="text-[13px] text-body">{label}</span>
      <span className="h-[9px] overflow-hidden rounded-bar bg-surface-alt" aria-hidden="true">
        <span
          data-bar=""
          className={`block h-full rounded-bar ${tone === "primary" ? "bg-primary" : "bg-line-strong"}`}
          style={{ width: `${width}%` }}
        />
      </span>
      <span className="text-end text-[15px] font-semibold tabular-nums text-ink">{pct(value)}</span>
    </div>
  );
}

/** ★3 v2: does ordering a correct work-up test change the diagnosis rate? Causal in the seeded cohort, observational for humans. */
export function KeyTest({ tests }: { tests: KeyTestEffect[] }) {
  const head = keyTestHeadline(tests);
  if (!head) return null;
  const others = tests.filter((t) => t.key !== head.key && typeof t.dx_accuracy_if_chosen === "number" && typeof t.dx_accuracy_if_not === "number");
  const main = tests.find((t) => t.key === head.key);

  return (
    <section
      aria-labelledby="key-test-title"
      className="relative overflow-hidden rounded-card border border-line bg-white shadow-card before:absolute before:inset-x-0 before:top-0 before:h-1 before:bg-brand-grad"
    >
      <div className="grid gap-8 p-5 pt-7 sm:p-8 sm:pt-9 lg:grid-cols-[1fr_1.1fr] lg:items-center">
        <div>
          <span className="font-mono text-eyebrow uppercase text-primary-hover">The key-test effect</span>
          <h2 id="key-test-title" className="mt-3 text-[clamp(21px,2.4vw,28px)] [overflow-wrap:anywhere]">
            Ordered {lowerFirst(head.test)} → right diagnosis {head.chosen} vs {head.notChosen}
          </h2>
          <p className="mt-3 text-[14.5px]">
            {head.sentence} {head.choseRate} of the cohort ordered it.
          </p>
        </div>
        <div className="space-y-3">
          <Bar label="Ordered it" value={main?.dx_accuracy_if_chosen} tone="primary" />
          <Bar label="Skipped it" value={main?.dx_accuracy_if_not} tone="muted" />
          <p className="pt-1 font-mono text-[10.5px] text-muted">share who named the right diagnosis</p>
          {others.length > 0 ? (
            <ul className="mt-2 space-y-1.5 border-t border-line pt-3 text-[13px]">
              {others.map((t) => (
                <li key={t.key} className="flex flex-wrap justify-between gap-x-3">
                  <span className="text-body">{t.text}</span>
                  <span className="font-mono text-[12px] tabular-nums text-muted">
                    {pct(t.dx_accuracy_if_chosen)} vs {pct(t.dx_accuracy_if_not)}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </section>
  );
}
