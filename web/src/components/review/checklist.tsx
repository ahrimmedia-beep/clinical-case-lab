import type { ReviewChecklistItem } from "@/lib/api/internal";
import { cn } from "@/lib/cn";
import type { CheckStatus } from "./review";

const META: Record<CheckStatus, { glyph: string; word: string; badge: string; tag: string; list: string }> = {
  ok: { glyph: "✓", word: "OK", badge: "bg-right text-white", tag: "border-right-border bg-right-tint text-primary-hover", list: "border-line bg-surface-alt" },
  warn: { glyph: "!", word: "Check", badge: "bg-missed text-white", tag: "border-missed-border bg-missed-tint text-missed-text", list: "border-missed-border bg-missed-tint" },
  fail: { glyph: "×", word: "Fail", badge: "bg-wrong text-white", tag: "border-wrong-border bg-wrong-tint text-wrong", list: "border-wrong-border bg-wrong-tint" },
};

/** Server-computed checks (no LLM): grounding, harmful options, no-leak, answer key, identifiers. Glyph + word + colour, never colour alone. */
export function Checklist({ items }: { items: ReviewChecklistItem[] }) {
  return (
    <ol className="divide-y divide-line">
      {items.map((item, i) => {
        const meta = META[item.status];
        const list = item.items ?? [];
        return (
          <li key={item.id} className="animate-rise px-5 py-4" style={{ animationDelay: `${i * 55}ms` }}>
            <div className="flex items-start gap-3">
              <span aria-hidden="true" className={cn("mt-0.5 flex size-[19px] flex-none items-center justify-center rounded-badge text-[11px] font-semibold", meta.badge)}>
                {meta.glyph}
              </span>
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2">
                  <span className="text-[14.5px] font-medium text-ink">{item.label}</span>
                  <span className={cn("rounded-[5px] border px-1.5 py-0.5 font-mono text-[9.5px] uppercase tracking-[.1em]", meta.tag)}>{meta.word}</span>
                </p>
                <p className="mt-1 text-[13.5px] text-body">{item.detail}</p>
                {list.length > 0 ? (
                  <ul className={cn("mt-2 space-y-1 rounded-[8px] border px-3 py-2", meta.list)}>
                    {list.map((entry) => (
                      <li key={entry} className="font-mono text-[11.5px] leading-snug text-ink [overflow-wrap:anywhere]">
                        {entry}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
