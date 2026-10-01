import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

const TONES = {
  time: "rounded-full bg-primary-tint px-[11px] py-[5px] text-[11px] font-semibold text-primary-deep",
  right: "rounded-full border border-right-border bg-right-tint py-1.5 pl-2 pr-[11px] text-[12.5px] font-semibold text-ink",
  wrong: "rounded-full border border-wrong-border bg-wrong-tint py-1.5 pl-2 pr-[11px] text-[12.5px] font-semibold text-ink",
  missed: "rounded-full border border-missed-border bg-missed-tint py-1.5 pl-2 pr-[11px] text-[12.5px] font-semibold text-ink",
  dark: "rounded-full border border-white/16 bg-white/8 px-3.5 py-[7px] font-mono text-[11px] tracking-[.09em] text-hero-text",
} as const;

export function Pill({ tone, children, className }: { tone: keyof typeof TONES; children: ReactNode; className?: string }) {
  return <span className={cn("inline-flex items-center gap-[7px] whitespace-nowrap leading-tight", TONES[tone], className)}>{children}</span>;
}
