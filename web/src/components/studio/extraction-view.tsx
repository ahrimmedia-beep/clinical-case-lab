"use client";

import { useActionState, useMemo, useState } from "react";
import { publishCase } from "@/app/studio/actions";
import { AnswerKeyList, type KeyStage } from "@/components/review/answer-key";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card, CardHeader } from "@/components/ui/card";
import { Eyebrow } from "@/components/ui/eyebrow";
import { ArrowIcon } from "@/components/ui/icons";
import { MonoTag } from "@/components/ui/mono-tag";
import { IDLE_PUBLISH, type PublishState } from "@/lib/action-states";
import type { EvidenceSpan, ExtractResponse } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { economics, factRows, groundingFor, phiSummary, type FactRow, type Grounding } from "@/lib/facts";
import { formatInt, modelLabel } from "@/lib/format";
import { HighlightedSource } from "./highlighted-source";

const GROUNDING: Record<Grounding, { label: string; tone: "teal" | "clay" | "neutral" }> = {
  grounded: { label: "in source", tone: "teal" },
  ungrounded: { label: "not in source", tone: "clay" },
  none: { label: "no quote", tone: "neutral" },
};

/**
 * Split view: the source with highlighted evidence on the left, what the model built on the right. Author view: shows the key.
 * `text` is the note exactly as submitted: "Publish" sends it back (with provider and model) instead of the case, so the
 * server republishes its own cached extraction and the browser never supplies case content.
 */
export function ExtractionView({ result, text }: { result: ExtractResponse; text: string }) {
  const [active, setActive] = useState<string | null>(null);
  const rows = useMemo(() => factRows(result.case), [result.case]);
  const stages = useMemo<KeyStage[]>(
    () =>
      result.case.decisions.map((d) => ({
        stage: d.stage,
        prompt: d.prompt,
        explanation: d.explanation,
        options: d.options ?? [],
        accepted: d.accepted_answers ?? [],
      })),
    [result.case.decisions],
  );
  const [publishState, publish, publishing] = useActionState<PublishState>(
    async () => (await publishCase({ text, provider: result.provider, model: result.model })) ?? IDLE_PUBLISH,
    IDLE_PUBLISH,
  );
  const eco = economics(result);

  const publishButton = (
    <form action={publish}>
      <Button type="submit" disabled={publishing} aria-busy={publishing}>
        {publishing ? (
          "Publishing…"
        ) : (
          <>
            Publish as draft <ArrowIcon />
          </>
        )}
      </Button>
    </form>
  );

  return (
    <section aria-labelledby="extraction-title" className="space-y-6">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Eyebrow>Draft case</Eyebrow>
          <MonoTag tone="clay">AI draft · not reviewed</MonoTag>
        </div>
        <h2 id="extraction-title" className="mt-2 text-[clamp(23px,2.6vw,30px)] [overflow-wrap:anywhere]">
          {result.case.title}
        </h2>
        <p className="mt-1 text-[13.5px] text-muted">
          {result.case.specialty} · {result.case.difficulty} · ~{result.case.estimated_minutes} min
        </p>
      </div>

      <section aria-label="What this draft cost" className="overflow-hidden rounded-card border border-line bg-white shadow-card">
        <dl className="grid grid-cols-3 divide-x divide-line">
          {[
            ["Draft in", eco.draftTime],
            ["Model cost", eco.cost],
            ["Facts grounded", eco.groundedLabel],
          ].map(([label, value]) => (
            <div key={label} className="px-4 py-4 sm:px-6 sm:py-5">
              <dt className="font-mono text-[10px] uppercase tracking-[.1em] text-muted sm:text-[10.5px]">{label}</dt>
              <dd className="mt-1.5 text-[clamp(22px,3.4vw,34px)] font-semibold leading-none tracking-[-.03em] text-ink tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-4 border-t border-line bg-surface-alt px-4 py-4 sm:px-6">
          <p className="min-w-0 flex-1 basis-[320px] text-[13.5px]">
            <b className="font-semibold text-ink">Faculty drafting takes hours.</b> This draft still goes to a physician, who checks the flagged
            items rather than rewriting the case. Nobody can play it for credit until they approve it.
          </p>
          {publishButton}
        </div>
      </section>
      <p className="-mt-3 font-mono text-[11px] text-muted [overflow-wrap:anywhere]">
        {modelLabel(result.model)} · prompt {result.prompt_version} · {formatInt(result.usage.input_tokens)} in · {formatInt(result.usage.output_tokens)} out
        tokens · masked: {phiSummary(result.phi)}
      </p>
      {publishState.status === "error" ? (
        <p role="alert" className="font-mono text-[12px] text-error">
          {publishState.message}
        </p>
      ) : null}

      {result.warnings.length > 0 ? (
        <Callout title="Check before publishing.">
          {result.warnings.map((w) => w.replace(/\.$/, "")).join(" · ")}. The reviewer sees this again on the checklist.
        </Callout>
      ) : null}

      <div className="grid items-start gap-6 lg:grid-cols-2">
        <Card className="lg:sticky lg:top-[88px]">
          <CardHeader title="De-identified source" tag={`masked: ${phiSummary(result.phi)}`} />
          <div className="px-5 py-4">
            <HighlightedSource text={result.source_text} spans={result.spans} active={active} onActive={setActive} />
            <p className="mt-4 font-mono text-[11px] text-muted">
              Highlights are the model&apos;s verbatim quotes, found in the text. Hover one to see its fact; dashed tokens were masked before the
              model saw the note.
            </p>
          </div>
        </Card>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Extracted facts" tag={`${rows.length} items`} />
            <FactList rows={rows} spans={result.spans} active={active} onActive={setActive} />
          </Card>
          <Card>
            <CardHeader title="Authored decisions" tag="answer key" />
            <AnswerKeyList stages={stages} finalDiagnosis={result.case.final_diagnosis.name} />
          </Card>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4 rounded-card border border-line bg-surface-alt px-5 py-4">
        <p className="text-[14px] text-ink">
          Looks right? Publish it as a draft; the physician review opens next.
        </p>
        {publishButton}
      </div>
    </section>
  );
}

type FactListProps = { rows: FactRow[]; spans: EvidenceSpan[]; active: string | null; onActive: (path: string | null) => void };

function FactList({ rows, spans, active, onActive }: FactListProps) {
  const groups = [...new Set(rows.map((r) => r.group))];
  return (
    <div className="divide-y divide-line">
      {groups.map((group) => (
        <div key={group} className="px-5 py-3">
          <p className="mb-1.5 font-mono text-[10.5px] uppercase tracking-[.1em] text-muted">{group}</p>
          <ul className="space-y-0.5">
            {rows
              .filter((r) => r.group === group)
              .map((row) => {
                const g = GROUNDING[groundingFor(row.path, spans)];
                return (
                  <li
                    key={row.path}
                    tabIndex={0}
                    onMouseEnter={() => onActive(row.path)}
                    onMouseLeave={() => onActive(null)}
                    onFocus={() => onActive(row.path)}
                    onBlur={() => onActive(null)}
                    className={cn(
                      "flex items-start gap-3 rounded-[8px] px-2 py-1.5 transition-colors",
                      active === row.path && "bg-primary-tint ring-1 ring-primary-border",
                    )}
                  >
                    <span className="w-[76px] flex-none pt-0.5 font-mono text-[10px] uppercase tracking-[.06em] text-muted sm:w-[84px]">{row.label}</span>
                    <span className="min-w-0 flex-1 text-[14px] text-ink [overflow-wrap:anywhere]">{row.text}</span>
                    <MonoTag tone={g.tone} className="mt-0.5">
                      {g.label}
                    </MonoTag>
                  </li>
                );
              })}
          </ul>
        </div>
      ))}
    </div>
  );
}
