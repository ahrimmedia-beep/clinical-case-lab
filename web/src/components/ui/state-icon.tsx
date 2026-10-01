import { cn } from "@/lib/cn";

export type Mark = "right" | "wrong" | "missed" | "neutral";

const GLYPH: Record<Mark, string> = { right: "✓", wrong: "×", missed: "+", neutral: "–" };
const LABEL: Record<Mark, string> = { right: "Right", wrong: "Wrong", missed: "Missed", neutral: "Not chosen" };
const STYLE: Record<Mark, string> = {
  right: "bg-right text-white",
  wrong: "bg-wrong text-white",
  missed: "bg-missed text-white",
  neutral: "border border-line bg-surface-alt text-muted",
};

/** One badge shape for every mark: the same glyph in the key, the stage row and the open stage. */
export function StateIcon({ state, label, className }: { state: Mark; label?: string; className?: string }) {
  return (
    <span
      role="img"
      aria-label={label ?? LABEL[state]}
      className={cn("flex size-[19px] flex-none items-center justify-center rounded-badge text-[11px] font-semibold leading-none", STYLE[state], className)}
    >
      {GLYPH[state]}
    </span>
  );
}
