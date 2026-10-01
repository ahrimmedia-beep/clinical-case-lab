import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

type Props = Omit<HTMLAttributes<HTMLDivElement>, "title"> & { title?: ReactNode; children: ReactNode };

export function Callout({ title, children, className, ...props }: Props) {
  return (
    <div className={cn("max-w-[560px] rounded-r-[8px] border-l-2 border-primary bg-surface-alt px-4 py-3.5 text-[14px] text-body", className)} {...props}>
      <p>
        {title ? <b className="font-semibold text-ink">{title} </b> : null}
        {children}
      </p>
    </div>
  );
}
