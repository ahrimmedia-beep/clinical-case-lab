"use client";

import { CheckIcon } from "@/components/ui/icons";
import type { PublicOption } from "@/lib/api/types";
import { cn } from "@/lib/cn";

type Props = { label: string; options: PublicOption[]; selected: string[]; disabled: boolean; onToggle: (key: string) => void };

/** Multi-select chips. Selection is a neutral teal tint only: nothing here says right or wrong. */
export function OptionChips({ label, options, selected, disabled, onToggle }: Props) {
  return (
    <div role="group" aria-label={label} className="mt-4 flex flex-col gap-1.5">
      {options.map((option) => {
        const on = selected.includes(option.key);
        return (
          <button
            key={option.key}
            type="button"
            role="checkbox"
            aria-checked={on}
            disabled={disabled}
            onClick={() => onToggle(option.key)}
            className={cn(
              "flex w-full items-start gap-3 rounded-input px-3 py-[9px] text-left transition-colors duration-150",
              on ? "bg-primary-tint ring-1 ring-primary-border" : "enabled:hover:bg-primary-tint",
              disabled && !on && "opacity-60",
            )}
          >
            <span
              aria-hidden="true"
              className={cn(
                "mt-[3px] flex size-[18px] flex-none items-center justify-center rounded-[5px] border bg-white",
                on ? "border-primary text-primary-hover" : "border-line-strong",
              )}
            >
              {on ? <CheckIcon className="size-3" /> : null}
            </span>
            <span className="min-w-0 flex-1 text-[15px] font-medium leading-[1.45] text-ink [overflow-wrap:anywhere]">{option.text}</span>
            <span className="mt-[3px] font-mono text-[10.5px] text-muted">{option.key}</span>
          </button>
        );
      })}
    </div>
  );
}
