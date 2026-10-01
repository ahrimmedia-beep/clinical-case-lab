import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

const TONES = {
  neutral: "border-line text-muted",
  teal: "border-primary-border bg-primary-tint text-primary-hover",
  clay: "border-wrong-border bg-wrong-tint text-wrong",
} as const;

export function MonoTag({ children, tone = "neutral", className }: { children: ReactNode; tone?: keyof typeof TONES; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-[6px] border px-[7px] py-1 font-mono text-[9.5px] uppercase leading-none tracking-[.1em]",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
