import { cn } from "@/lib/cn";

export type BarSegment = { tone: "right" | "wrong" | "missed"; value: number };

const TONE: Record<BarSegment["tone"], string> = { right: "bg-right", wrong: "bg-wrong", missed: "bg-missed" };

type Props = { segments: readonly BarSegment[]; label: string; size?: "lg" | "sm"; delayMs?: number };

/** Teal / clay / amber bar; each segment's width is proportional to its count and grows from the left. */
export function SegmentedBar({ segments, label, size = "lg", delayMs = 0 }: Props) {
  const shown = segments.filter((s) => s.value > 0);
  return (
    // A <span>, not a <div>: the bar also sits inside the debrief's row <button>, which only allows phrasing content.
    <span role="img" aria-label={label} className={cn("flex w-full", size === "lg" ? "h-[9px] gap-[3px]" : "h-[5px] gap-[2px]")}>
      {shown.length === 0 ? (
        <i className="block h-full flex-1 rounded-bar bg-line" />
      ) : (
        shown.map((s, i) => (
          <i
            key={s.tone}
            className={cn("block h-full origin-left animate-grow-x", size === "lg" ? "rounded-bar" : "rounded-[2px]", TONE[s.tone])}
            style={{ flex: s.value, animationDelay: `${delayMs + i * 100}ms` }}
          />
        ))
      )}
    </span>
  );
}
