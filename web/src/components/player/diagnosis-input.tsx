"use client";

import { useId } from "react";
import { DIAGNOSIS_MAX } from "./state";

type Props = { value: string; disabled: boolean; onChange: (value: string) => void };

export function DiagnosisInput({ value, disabled, onChange }: Props) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-[14px] font-medium text-ink">
        Your diagnosis
      </label>
      <input
        id={id}
        type="text"
        value={value}
        maxLength={DIAGNOSIS_MAX}
        autoComplete="off"
        spellCheck={false}
        disabled={disabled}
        placeholder="Name the condition"
        aria-describedby={`${id}-count`}
        onChange={(event) => onChange(event.target.value)}
        className="h-[42px] w-full rounded-input border border-line bg-surface-alt px-[13px] text-[15px] text-ink outline-none transition focus:border-primary focus:bg-white disabled:opacity-80"
      />
      <p id={`${id}-count`} className="mt-1 text-end font-mono text-[11px] text-muted">
        {value.length}/{DIAGNOSIS_MAX}
      </p>
    </div>
  );
}
