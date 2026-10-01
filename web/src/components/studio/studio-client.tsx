"use client";

import { useActionState, useId, useState } from "react";
import { extractCase } from "@/app/studio/actions";
import { Button } from "@/components/ui/button";
import type { StudioSample } from "@/data/studio-samples";
import { IDLE_EXTRACT } from "@/lib/action-states";
import type { Provider } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatRatio } from "@/lib/format";
import { ExtractionView } from "./extraction-view";
import { StepProgress } from "./step-progress";

const PROVIDERS: { value: Provider; label: string; hint: string }[] = [
  { value: "gemini", label: "Gemini 3.8 Flash", hint: "fast, about $0.01 a case" },
  { value: "claude", label: "Claude Sonnet 5", hint: "about $0.02 a case" },
];

export function StudioClient({ samples }: { samples: StudioSample[] }) {
  const [text, setText] = useState(samples[0]?.text ?? "");
  const [provider, setProvider] = useState<Provider>("gemini");
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [state, formAction, pending] = useActionState(extractCase, IDLE_EXTRACT);
  const textId = useId();
  const fieldErrors = state.status === "error" ? state.fieldErrors : {};
  const result = state.status === "done" ? state.result : null;
  const status =
    result && !pending
      ? `Draft built: ${result.spans.length} quoted facts, ${formatRatio(result.grounded_ratio)} found in the source.`
      : pending
        ? "Building the draft."
        : "";

  return (
    <div className="space-y-10">
      <form action={formAction} onSubmit={() => setStartedAt(Date.now())} className="rounded-card border border-line bg-white p-5 shadow-card sm:p-6">
        <fieldset>
          <legend className="mb-2 font-mono text-[11px] uppercase tracking-[.1em] text-muted">Samples · synthetic notes</legend>
          <div className="flex flex-wrap gap-2">
            {samples.map((sample) => (
              <button
                key={sample.id}
                type="button"
                aria-pressed={text === sample.text}
                onClick={() => setText(sample.text)}
                className={cn(
                  "rounded-full border px-3.5 py-2.5 text-[13px] transition-colors",
                  text === sample.text ? "border-primary-border bg-primary-tint text-primary-deep" : "border-line text-body hover:bg-surface-alt",
                )}
              >
                {sample.label}
              </button>
            ))}
          </div>
        </fieldset>

        <label htmlFor={textId} className="mb-2 mt-5 block text-[14px] font-medium text-ink">
          Clinical text
        </label>
        <textarea
          id={textId}
          name="text"
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={9}
          maxLength={20_000}
          aria-invalid={Boolean(fieldErrors.text)}
          aria-describedby={`${textId}-hint`}
          className="w-full rounded-input border border-line bg-surface-alt px-[13px] py-3 font-mono text-[16px] leading-[1.6] text-ink outline-none transition focus:border-primary focus:bg-white sm:text-[13px] aria-[invalid=true]:border-error"
        />
        <div id={`${textId}-hint`} className="mt-1 flex justify-between gap-3 font-mono text-[11px] text-muted">
          <span className={fieldErrors.text ? "text-error" : undefined}>
            {fieldErrors.text?.[0] ?? "50 to 20,000 characters. Synthetic text only: never paste a real patient's note."}
          </span>
          <span className="flex-none">{text.length.toLocaleString("en-US")}/20,000</span>
        </div>

        <div className="mt-5 flex flex-wrap items-end gap-4">
          <fieldset>
            <legend className="mb-2 text-[14px] font-medium text-ink">Model</legend>
            <div className="inline-flex flex-wrap rounded-btn border border-line-strong p-1">
              {PROVIDERS.map((p) => (
                <label
                  key={p.value}
                  className={cn(
                    "cursor-pointer rounded-[7px] px-3.5 py-2.5 text-[13.5px] font-medium transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-primary",
                    provider === p.value ? "bg-primary-tint text-primary-deep" : "text-body hover:bg-surface-alt",
                  )}
                >
                  <input
                    type="radio"
                    name="provider"
                    value={p.value}
                    checked={provider === p.value}
                    onChange={() => setProvider(p.value)}
                    className="sr-only"
                  />
                  {p.label}
                  <span className="ml-1.5 hidden font-mono text-[10.5px] font-normal text-muted sm:inline">{p.hint}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <Button type="submit" disabled={pending} aria-busy={pending} className="ml-auto">
            {pending ? "Building the draft…" : "Extract case"}
          </Button>
        </div>
        {state.status === "error" ? (
          <p role="alert" className="mt-4 font-mono text-[12px] text-error">
            {state.message}
          </p>
        ) : null}
      </form>

      <p role="status" aria-live="polite" className="sr-only">
        {status}
      </p>
      {pending || result ? <StepProgress pending={pending} startedAt={startedAt} result={result} /> : null}
      {result && !pending ? <ExtractionView key={`${result.model}:${result.case.title}:${result.usage.input_tokens}`} result={result} /> : null}
    </div>
  );
}
