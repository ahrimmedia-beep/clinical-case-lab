import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export type ButtonVariant = "primary" | "primary-sm" | "ghost" | "ghost-sm" | "on-dark" | "on-dark-ghost" | "link";

const BASE = "inline-flex items-center justify-center gap-2 disabled:pointer-events-none disabled:opacity-50";

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "rounded-btn bg-primary px-[26px] py-3.5 text-[14.5px] font-medium text-white transition duration-200 hover:-translate-y-px hover:bg-primary-hover hover:shadow-btn",
  "primary-sm":
    "rounded-[8px] bg-primary px-[18px] py-[10.5px] text-[13.5px] font-medium text-white transition duration-200 hover:-translate-y-px hover:bg-primary-hover hover:shadow-btn",
  ghost:
    "rounded-btn border border-line-strong bg-transparent px-[26px] py-3.5 text-[14.5px] font-medium text-ink transition duration-200 hover:border-ink hover:bg-surface-alt",
  "ghost-sm":
    "rounded-[8px] border border-line-strong bg-transparent px-[18px] py-[10.5px] text-[13.5px] font-medium text-ink transition duration-200 hover:border-ink hover:bg-surface-alt",
  "on-dark":
    "rounded-[11px] bg-white px-6 py-[15px] text-[15.5px] font-semibold text-primary-deep shadow-[0_14px_34px_rgba(2,32,28,.34)] transition duration-200 hover:-translate-y-px",
  "on-dark-ghost":
    "rounded-[11px] border border-white/35 px-[22px] py-3.5 text-[14.5px] font-medium text-hero-text transition duration-200 hover:border-white hover:bg-white/8",
  link:
    "border-b border-primary-border pb-[3px] text-[14.5px] font-medium text-primary-hover transition-[gap] duration-200 hover:gap-3 hover:border-primary-hover",
};

export function buttonClasses(variant: ButtonVariant = "primary", className?: string): string {
  return cn(BASE, VARIANTS[variant], className);
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant };

export function Button({ variant = "primary", className, type = "button", ...props }: ButtonProps) {
  return <button type={type} className={buttonClasses(variant, className)} {...props} />;
}
