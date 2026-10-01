import Link from "next/link";
import { buttonClasses } from "@/components/ui/button";

/** Shown instead of a crash when the API is down, slow or failing (Review Focus #2). */
export function ServiceUnavailable({ message, retryHref }: { message: string; retryHref: string }) {
  return (
    <div role="alert" className="max-w-[560px] rounded-card border border-line bg-surface-alt px-6 py-6">
      <p className="font-mono text-[11px] uppercase tracking-[.1em] text-muted">Service status</p>
      <h2 className="mt-2 text-[19px]">The case service is not answering</h2>
      <p className="mt-2 text-[14px] text-body">{message}</p>
      <Link href={retryHref} prefetch={false} className={buttonClasses("ghost-sm", "mt-4")}>
        Try again
      </Link>
    </div>
  );
}
