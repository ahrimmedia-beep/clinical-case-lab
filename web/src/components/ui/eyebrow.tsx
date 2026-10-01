import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Eyebrow({ children, onDark = false, className }: { children: ReactNode; onDark?: boolean; className?: string }) {
  return (
    <span className={cn("inline-block font-mono text-eyebrow uppercase", onDark ? "text-primary-lit" : "text-primary-hover", className)}>
      {children}
    </span>
  );
}
