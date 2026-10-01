import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Card({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <section className={cn("overflow-hidden rounded-card border border-line bg-white shadow-lift", className)} {...props} />;
}

type CardHeaderProps = {
  title: ReactNode;
  tag?: ReactNode;
  as?: "h2" | "h3";
  titleId?: string;
  className?: string;
  children?: ReactNode;
};

export function CardHeader({ title, tag, as: Heading = "h2", titleId, className, children }: CardHeaderProps) {
  return (
    <header className={cn("flex flex-wrap items-center gap-2.5 border-b border-line bg-surface-alt px-5 py-[13px]", className)}>
      <Heading id={titleId} className="text-[14.5px] font-semibold leading-tight tracking-[-.015em] text-ink">
        {title}
      </Heading>
      {children}
      {tag ? (
        <span className="ml-auto rounded-[5px] border border-line-strong px-[7px] py-0.5 font-mono text-[10px] uppercase tracking-[.11em] text-muted">
          {tag}
        </span>
      ) : null}
    </header>
  );
}

export function CardBody({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-5 py-4", className)} {...props} />;
}
