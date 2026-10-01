"use client";

import { useId, useState } from "react";
import { Card, CardHeader } from "@/components/ui/card";
import { ChevronIcon } from "@/components/ui/icons";
import { MonoTag } from "@/components/ui/mono-tag";
import { Pill } from "@/components/ui/pill";
import { SegmentedBar } from "@/components/ui/segmented-bar";
import { StateIcon, type Mark } from "@/components/ui/state-icon";
import type { AttemptResult, DebriefOption, DebriefStage, StageItem } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatPickRate, pluralize, stageNo } from "@/lib/format";
import { useCountUp } from "./use-count-up";

const GROUPS: { state: Mark; label: string }[] = [
  { state: "right", label: "right" },
  { state: "wrong", label: "wrong" },
  { state: "missed", label: "missed" },
  { state: "neutral", label: "not chosen, not needed" },
];

const ROW = "grid w-full grid-cols-[22px_minmax(0,1fr)_88px_14px] items-center gap-3 rounded-row px-3 py-2 text-left";

type Props = { result: AttemptResult; revealedStages: ReadonlySet<string> };

export function DebriefCard({ result, revealedStages }: Props) {
  const titleId = useId();
  const score = useCountUp(result.points);
  const [open, setOpen] = useState<string | null>(null);

  return (
    <Card aria-labelledby={titleId}>
      <CardHeader as="h3" titleId={titleId} title="Case debrief" tag="Your attempt" />
      <div className="border-b border-line px-5 pb-[15px] pt-[17px]">
        <p className="mb-[7px] flex animate-rise flex-wrap items-end gap-x-2.5 gap-y-1">
          <strong className="text-score text-ink" aria-hidden="true">
            {score}
            <span>/</span>
            {result.max_points}
          </strong>
          <span className="sr-only">
            {result.points} of {result.max_points} points
          </span>
          <span className="pb-[5px] text-sm2 text-muted">points — from diagnosis and treatment plan</span>
        </p>
        <p className="mb-[11px] max-w-[430px] animate-rise text-[12.5px] leading-[1.45] text-muted [animation-delay:80ms]">
          Every other stage is marked the same way and carries no points — {pluralize(result.total_decisions, "decision")} in total.
        </p>
        <SegmentedBar
          label={`${result.right} right, ${result.wrong} wrong, ${result.missed} missed`}
          delayMs={340}
          segments={[
            { tone: "right", value: result.right },
            { tone: "wrong", value: result.wrong },
            { tone: "missed", value: result.missed },
          ]}
        />
        <ul className="mt-3 flex flex-wrap gap-1.5">
          <li className="flex min-w-0 flex-1">
            <Pill tone="right" className="w-full"><StateIcon state="right" />{result.right} right</Pill>
          </li>
          <li className="flex min-w-0 flex-1">
            <Pill tone="wrong" className="w-full"><StateIcon state="wrong" />{result.wrong} wrong</Pill>
          </li>
          <li className="flex min-w-0 flex-1">
            <Pill tone="missed" className="w-full"><StateIcon state="missed" />{result.missed} missed</Pill>
          </li>
        </ul>
        <p className="mt-[9px] text-[11.5px] leading-[1.4] text-muted">Missed — correct here, you never chose it.</p>
        {result.harmful > 0 ? (
          <p className="mt-3 flex items-center gap-2 rounded-row border border-wrong-border bg-wrong-tint px-3 py-2 text-[13px] text-ink">
            <StateIcon state="wrong" label="Could harm" />
            {pluralize(result.harmful, "choice")} you made could harm this patient. The stage rows below show which.
          </p>
        ) : null}
        {result.diagnosis.hedged ? (
          <p className="mt-3 flex items-center gap-2 rounded-row border border-missed-border bg-missed-tint px-3 py-2 text-[13px] text-ink">
            <StateIcon state="missed" label="Hedged" />
            You named several diagnoses — hedging earns no points.
          </p>
        ) : null}
      </div>
      <ol className="px-2.5 pb-1.5 pt-1">
        {result.stages.map((stage, index) => (
          <StageRow
            key={stage.key}
            stage={stage}
            index={index}
            result={result}
            revealed={revealedStages.has(stage.key)}
            open={open === stage.key}
            onToggle={() => setOpen((current) => (current === stage.key ? null : stage.key))}
          />
        ))}
      </ol>
    </Card>
  );
}

type RowProps = {
  stage: DebriefStage;
  index: number;
  result: AttemptResult;
  revealed: boolean;
  open: boolean;
  onToggle: () => void;
};

function StageRow({ stage, index, result, revealed, open, onToggle }: RowProps) {
  const panelId = useId();
  const given = stage.kind === "given";
  // A given stage is read-only, unless an item was withheld during play: then the debrief reveals it.
  const expandable = given ? revealed && (stage.items ?? []).length > 0 : true;
  const total = stage.right + stage.missed;

  const head = (
    <>
      <span className="font-mono text-[10.5px] text-muted">{stageNo(stage.number)}</span>
      <span className="min-w-0">
        <b className={cn("block text-[14px] leading-[1.3] tracking-[-.012em]", given ? "font-normal text-body" : "font-medium text-ink")}>
          {stage.label}
        </b>
        {given ? null : <span className="mt-px block text-[11.5px] leading-[1.35] text-muted">{stage.hint}</span>}
      </span>
      <span className="text-end">
        {given ? (
          <span className="font-mono text-[9.5px] uppercase tracking-[.09em] text-muted">{revealed ? "Revealed now" : "Given to you"}</span>
        ) : (
          <>
            <span className="whitespace-nowrap text-[13px] font-medium text-ink">
              {stage.right} <span className="font-normal text-muted">of {total} right</span>
            </span>
            <span className="mt-1.5 block">
              <SegmentedBar
                size="sm"
                label={`${stage.right} right, ${stage.wrong} wrong, ${stage.missed} missed`}
                delayMs={700 + index * 55}
                segments={[
                  { tone: "right", value: stage.right },
                  { tone: "wrong", value: stage.wrong },
                  { tone: "missed", value: stage.missed },
                ]}
              />
            </span>
          </>
        )}
      </span>
      <ChevronIcon className={cn("text-muted transition-transform duration-300", open && "rotate-90 text-primary-hover", !expandable && "invisible")} />
    </>
  );

  return (
    <li className={cn("animate-rise rounded-row", open && "bg-surface-alt")} style={{ animationDelay: `${420 + index * 55}ms` }}>
      {expandable ? (
        <button type="button" aria-expanded={open} aria-controls={panelId} onClick={onToggle} className={cn(ROW, !open && "hover:bg-surface-alt")}>
          {head}
        </button>
      ) : (
        <div className={cn(ROW, "py-1.5")}>{head}</div>
      )}
      {open ? (
        <div id={panelId} className="pb-3 pl-[46px] pr-3.5">
          {given ? (
            <RevealedItems items={stage.items ?? []} />
          ) : stage.key === "diagnosis" ? (
            <DiagnosisDetail stage={stage} result={result} />
          ) : (
            <OptionGroups stage={stage} />
          )}
        </div>
      ) : null}
    </li>
  );
}

function OptionGroups({ stage }: { stage: DebriefStage }) {
  const revealLabel = stage.key === "interview" ? "Answer" : "Result";
  const options = stage.options ?? [];
  return (
    <div>
      {stage.explanation ? <p className="mb-2 text-[13px] leading-[1.55] text-body">{stage.explanation}</p> : null}
      {GROUPS.map(({ state, label }) => {
        const grouped = options.filter((o) => o.state === state);
        if (grouped.length === 0) return null;
        return (
          <div key={state} className="border-t border-line py-2">
            <p className="flex items-center gap-2 text-[12.5px] font-semibold text-ink">
              <StateIcon state={state} />
              {grouped.length} {label}
            </p>
            <ul className="mt-1.5 space-y-1.5">
              {grouped.map((option) => (
                <OptionLine key={option.key} option={option} revealLabel={revealLabel} />
              ))}
            </ul>
          </div>
        );
      })}
      <p className="mt-1 text-[11px] leading-[1.4] text-muted">Peer rates come from everyone who closed this case.</p>
    </div>
  );
}

function OptionLine({ option, revealLabel }: { option: DebriefOption; revealLabel: string }) {
  const pick = formatPickRate(option.pick_rate);
  return (
    <li className="rounded-[8px] bg-white px-3 py-2 ring-1 ring-line">
      <p className="text-[13.5px] font-medium leading-[1.4] text-ink [overflow-wrap:anywhere]">
        <span className="mr-1.5 font-mono text-[11px] font-normal text-muted">{option.key}</span>
        {option.text}
        {option.is_harmful ? <MonoTag tone="clay" className="ml-2 align-middle">could harm</MonoTag> : null}
      </p>
      {option.feedback ? <p className="mt-1 text-[12.5px] leading-[1.5] text-body">{option.feedback}</p> : null}
      {option.reveal ? (
        <p className="mt-1 text-[12.5px] text-muted [overflow-wrap:anywhere]">
          <span className="font-mono text-[10px] uppercase tracking-[.08em]">{revealLabel}</span> · {option.reveal}
        </p>
      ) : null}
      {pick ? (
        <p className="mt-1.5 flex items-center gap-2">
          <span className="h-[3px] w-16 overflow-hidden rounded-full bg-line">
            <span className="block h-full bg-muted/60" style={{ width: `${Math.round((option.pick_rate ?? 0) * 100)}%` }} />
          </span>
          <span className="font-mono text-[10.5px] text-muted">{pick}</span>
        </p>
      ) : null}
    </li>
  );
}

function DiagnosisDetail({ stage, result }: { stage: DebriefStage; result: AttemptResult }) {
  const mark: Mark = !result.diagnosis.answered ? "missed" : result.diagnosis.correct ? "right" : "wrong";
  return (
    <div className="space-y-2 text-[13.5px]">
      {stage.explanation ? <p className="leading-[1.55] text-body">{stage.explanation}</p> : null}
      <p className="flex items-start gap-2 border-t border-line pt-2">
        <StateIcon state={mark} />
        <span className="min-w-0 [overflow-wrap:anywhere]">
          <span className="text-muted">Your call: </span>
          <span className="font-medium text-ink">{result.diagnosis.answered ? result.diagnosis.your_text : "none given"}</span>
        </span>
      </p>
      {result.diagnosis.hedged ? (
        <p className="flex items-start gap-2 text-missed-text">
          <StateIcon state="missed" label="Hedged" />
          You named several diagnoses — hedging earns no points.
        </p>
      ) : null}
      <p className="text-muted">
        Final diagnosis: <span className="font-medium text-ink">{result.final_diagnosis.name}</span>
      </p>
    </div>
  );
}

function RevealedItems({ items }: { items: StageItem[] }) {
  return (
    <ul className="space-y-1.5 border-t border-line pt-2 text-[13.5px]">
      {items.map((item, i) => (
        <li key={`${item.text}-${i}`} className="[overflow-wrap:anywhere]">
          <span className="text-ink">{item.text}</span>
          {item.value ? (
            <span className="ml-1.5 text-muted">
              {item.value}
              {item.unit ? ` ${item.unit}` : ""}
            </span>
          ) : null}
        </li>
      ))}
      <li className="pt-1 text-[11.5px] text-muted">Hidden during the case because it would have named the diagnosis.</li>
    </ul>
  );
}
