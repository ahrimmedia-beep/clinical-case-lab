"use client";

import { useEffect, useRef } from "react";
import { CheckIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { stageNo } from "@/lib/format";
import { stageStatus, type PlayerState } from "./state";

const STATUS_TEXT = { current: ", current stage", done: ", done", open: "", upcoming: ", not reached yet" } as const;

/** Nine numbered stages: a left rail from 1024 px, a compact top stepper below. Only visited stages are clickable.
 * The top stepper scrolls sideways rather than squeezing nine buttons under 40px: each stays a full tap target,
 * and the current one scrolls into view as it changes. */
export function StageRail({ state, onGo }: { state: PlayerState; onGo: (index: number) => void }) {
  const frozen = state.phase !== "playing";
  const currentRef = useRef<HTMLLIElement>(null);
  const currentIndex = state.current; // local, non-".current" name so exhaustive-deps doesn't mistake it for a ref
  useEffect(() => {
    currentRef.current?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [currentIndex]);
  // min-w-0 on <nav>: a grid/flex item's implicit min-width is its content's intrinsic size, so without
  // it the nine-button stepper (392px of buttons+gaps) forces the whole grid item — and the page —
  // wider than the viewport on phones instead of scrolling inside its own overflow-x-auto.
  return (
    <nav aria-label="Case stages" className="min-w-0">
      <ol className="flex gap-1 overflow-x-auto lg:hidden">
        {state.stages.map((stage, index) => {
          const status = stageStatus(state, index);
          return (
            <li key={stage.key} ref={status === "current" ? currentRef : undefined} className="flex-none">
              <button
                type="button"
                disabled={frozen || index > state.visited}
                onClick={() => onGo(index)}
                aria-current={status === "current" ? "step" : undefined}
                aria-label={`${stageNo(stage.number)} ${stage.label}${STATUS_TEXT[status]}`}
                className={cn(
                  "flex size-10 items-center justify-center rounded-[7px] font-mono text-[10.5px] transition-colors",
                  status === "current" && "bg-white text-ink ring-2 ring-primary",
                  status === "done" && "bg-primary-tint text-primary-hover",
                  status === "open" && "bg-white text-ink ring-1 ring-line-strong",
                  status === "upcoming" && "bg-surface-alt text-muted",
                )}
              >
                {status === "done" ? <CheckIcon className="size-3" /> : stageNo(stage.number)}
              </button>
            </li>
          );
        })}
      </ol>

      <ol className="sticky top-[96px] hidden space-y-0.5 lg:block">
        {state.stages.map((stage, index) => {
          const status = stageStatus(state, index);
          const reachable = !frozen && index <= state.visited;
          return (
            <li key={stage.key}>
              <button
                type="button"
                disabled={!reachable}
                onClick={() => onGo(index)}
                aria-current={status === "current" ? "step" : undefined}
                className={cn(
                  "grid w-full grid-cols-[26px_minmax(0,1fr)_16px] items-center gap-2.5 rounded-row px-2.5 py-2 text-left transition-colors",
                  reachable && status !== "current" && "hover:bg-surface-alt",
                )}
              >
                <span className={cn("flex size-[26px] items-center justify-center rounded-full font-mono text-[10.5px]", status === "current" ? "text-ink ring-2 ring-primary" : "text-muted")}>
                  {stageNo(stage.number)}
                </span>
                <span className="min-w-0">
                  <span
                    className={cn(
                      "block truncate text-[14px] leading-tight",
                      status === "current" ? "font-semibold text-ink" : status === "upcoming" ? "text-muted" : stage.kind === "given" ? "text-body" : "font-medium text-ink",
                    )}
                  >
                    {stage.label}
                  </span>
                  <span className="block truncate text-[11.5px] text-muted">{stage.kind === "given" ? "given to you" : stage.hint}</span>
                </span>
                {status === "done" ? (
                  <span className="flex size-4 items-center justify-center rounded-full bg-primary-tint text-primary-hover">
                    <CheckIcon className="size-2.5" />
                    <span className="sr-only">done</span>
                  </span>
                ) : (
                  <span />
                )}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
