"use client";

import { useId } from "react";
import { cn } from "@/lib/cn";

const LEVELS = [1, 2, 3, 4, 5] as const;

type Props = { value: number | null; disabled: boolean; onChange: (value: number) => void };

/** Native radios (arrow keys work) styled as the 1–5 selector from the Eximion app. */
export function ConfidenceSelector({ value, disabled, onChange }: Props) {
  const name = useId();
  return (
    <fieldset disabled={disabled}>
      <legend className="mb-2 text-[14px] font-medium text-ink">How sure are you?</legend>
      <div className="grid grid-cols-5 gap-1.5">
        {LEVELS.map((level) => (
          <label
            key={level}
            className={cn(
              "cursor-pointer rounded-[8px] border py-2.5 text-center text-[14px] font-semibold transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary",
              value === level ? "border-primary bg-primary text-white" : "border-line-strong bg-white text-ink hover:bg-surface-alt",
              disabled && "cursor-default opacity-70",
            )}
          >
            <input type="radio" name={name} value={level} checked={value === level} onChange={() => onChange(level)} className="sr-only" />
            {level}
          </label>
        ))}
      </div>
      <div className="mt-1.5 flex justify-between text-[12px] text-muted">
        <span>guessing</span>
        <span>certain</span>
      </div>
    </fieldset>
  );
}
