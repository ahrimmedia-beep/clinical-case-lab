"use client";

import Link from "next/link";
import { useEffect } from "react";
import { Button, buttonClasses } from "@/components/ui/button";

export default function CaseError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div className="mx-auto max-w-site px-4 py-16 sm:px-6">
      <div role="alert" className="max-w-[560px] rounded-card border border-line bg-surface-alt p-6">
        <p className="font-mono text-[11px] uppercase tracking-[.1em] text-muted">Something broke</p>
        <h1 className="mt-2 text-[22px]">This case didn&apos;t load</h1>
        <p className="mt-2 text-[14px] text-body">The problem is on our side. Try again, or pick another case.</p>
        <div className="mt-4 flex flex-wrap gap-3">
          <Button variant="primary-sm" onClick={reset}>Try again</Button>
          <Link href="/cases" className={buttonClasses("ghost-sm")}>All cases</Link>
        </div>
      </div>
    </div>
  );
}
