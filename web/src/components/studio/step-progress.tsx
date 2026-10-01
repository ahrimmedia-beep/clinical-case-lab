"use client";

import { useEffect, useState } from "react";
import { CheckIcon } from "@/components/ui/icons";
import type { ExtractResponse } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { finishedSteps, runningSteps, type StepState } from "@/lib/facts";
import { formatMs } from "@/lib/format";

type Props = { pending: boolean; startedAt: number | null; result: ExtractResponse | null };

function Marker({ state }: { state: StepState }) {
  if (state === "done") {
    return (
      <span className="flex size-6 items-center justify-center rounded-full bg-primary text-white">
        <CheckIcon className="size-3" />
      </span>
    );
  }
  if (state === "warn") {
    return <span className="flex size-6 items-center justify-center rounded-full bg-missed text-[12px] font-semibold text-white">!</span>;
  }
  if (state === "running") {
    return (
      <span className="relative flex size-6 items-center justify-center rounded-full border-2 border-primary bg-white">
        <span aria-hidden="true" className="absolute inset-0 animate-ping-soft rounded-full border border-primary" />
        <span className="size-2 rounded-full bg-primary" />
      </span>
    );
  }
  return <span className="block size-6 rounded-full border border-line-strong bg-white" />;
}

const STATE_TEXT: Record<StepState, string> = { waiting: "waiting", running: "running", done: "done", warn: "done, needs a look" };

/** de-identify → extract → ground → author → validate. Estimated while running; exact (what each step produced) once done. */
export function StepProgress({ pending, startedAt, result }: Props) {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    if (!pending) return;
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [pending]);

  const elapsed = pending && startedAt !== null && now !== null ? Math.max(0, now - startedAt) : 0;
  const steps = !pending && result ? finishedSteps(result) : runningSteps(elapsed);

  return (
    <section aria-label="Pipeline steps" className="rounded-card border border-line bg-white px-5 py-5 shadow-card sm:px-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[14.5px] font-semibold tracking-[-.015em]">{pending ? "Building the draft" : "Draft built"}</h2>
        <span className="font-mono text-[11px] tabular-nums text-muted">
          {pending ? `${Math.floor(elapsed / 1000)} s` : result ? `finished in ${formatMs(result.usage.latency_ms)}` : ""}
        </span>
      </div>
      <ol className="mt-5 grid gap-4 md:grid-cols-5 md:gap-3">
        {steps.map((step, i) => (
          <li key={step.key} className="relative flex gap-3 md:flex-col md:gap-2.5">
            {i < steps.length - 1 ? (
              <span
                aria-hidden="true"
                className={cn(
                  "absolute bg-line md:left-8 md:right-1 md:top-3 md:h-px md:w-auto",
                  "left-3 top-8 h-[calc(100%-16px)] w-px md:bottom-auto",
                  (step.state === "done" || step.state === "warn") && "bg-primary-border",
                )}
              />
            ) : null}
            <Marker state={step.state} />
            <div className="min-w-0">
              <p className={cn("text-[14px] font-medium", step.state === "waiting" ? "text-muted" : "text-ink")}>
                <span className="mr-1.5 font-mono text-[10.5px] text-muted">{String(i + 1).padStart(2, "0")}</span>
                {step.label}
                <span className="sr-only">, {STATE_TEXT[step.state]}</span>
              </p>
              {step.detail ? <p className="mt-0.5 font-mono text-[11px] leading-snug text-muted [overflow-wrap:anywhere]">{step.detail}</p> : null}
            </div>
          </li>
        ))}
      </ol>
      {pending ? (
        <p className="mt-4 border-t border-line pt-3 text-[12.5px] text-muted">
          The steps run on the server, so the highlighted one is an estimate until the response arrives. Repeated samples come back from the
          cache at once.
        </p>
      ) : null}
    </section>
  );
}
