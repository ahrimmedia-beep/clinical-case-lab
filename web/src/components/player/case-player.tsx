"use client";

import { startTransition, useActionState, useId, useMemo, useReducer, useRef, useState, useTransition, type ReactNode } from "react";
import { revealOptions, submitAttempt } from "@/app/actions";
import { CaseFileCard, type CaseFileHint } from "@/components/case/case-file-card";
import { DebriefView } from "@/components/debrief/debrief-view";
import { Button } from "@/components/ui/button";
import { ArrowIcon } from "@/components/ui/icons";
import { MonoTag } from "@/components/ui/mono-tag";
import { StateIcon } from "@/components/ui/state-icon";
import { IDLE_SUBMIT, type SubmitState } from "@/lib/action-states";
import type { CasePublic, PublicStage, Stage } from "@/lib/api/types";
import { isRevealStage } from "@/lib/api/types";
import { stageNo } from "@/lib/format";
import { ConfidenceSelector } from "./confidence-selector";
import { DiagnosisInput } from "./diagnosis-input";
import { OptionChips } from "./option-chips";
import { RevealList } from "./reveal-list";
import { clearSavedResult, saveResult, useSavedResult } from "./saved-result";
import { StageRail } from "./stage-rail";
import {
  attemptToFormData,
  canAdvance,
  canClose,
  canLock,
  closeRequest,
  initPlayer,
  playerReducer,
  withheldStageKeys,
  type PlayerAction,
  type PlayerState,
} from "./state";

export type GivenSlots = Partial<Record<Stage, ReactNode>>;

type Props = { caseData: CasePublic; given: GivenSlots };

/**
 * Client stepper for one case. Given stages arrive already rendered by the server (`given`):
 * Server Components passed into a Client Component as props. Decisions live in the pure
 * reducer (state.ts); the answers leave the browser once, through the submitAttempt Server Action.
 */
export function CasePlayer({ caseData, given }: Props) {
  const [round, setRound] = useState(0);
  return (
    <PlayerRound
      key={round}
      caseData={caseData}
      given={given}
      onPlayAgain={() => {
        clearSavedResult(caseData.slug);
        setRound((r) => r + 1);
      }}
    />
  );
}

function introHints(stages: PublicStage[]): CaseFileHint[] {
  return stages
    .filter((s) => s.kind === "decision")
    .map((s) => ({
      label: s.label,
      hint: s.input === "free_text" ? "free text · rate confidence" : `${(s.options ?? []).length} options${s.scored ? " · scored" : ""}`,
    }));
}

/** C1 delta (amendments §E): visible for the whole play session, not just the intro, so a
 * physician never mistakes an AI-drafted, unreviewed case for a scored one. */
function DraftBanner() {
  return (
    <div
      role="status"
      className="mb-5 flex items-center justify-center gap-2 rounded-row border border-missed-border bg-missed-tint px-4 py-2.5 text-center font-mono text-[11.5px] text-missed-text"
    >
      <StateIcon state="missed" label="Draft" />
      AI draft · not physician-reviewed — scores are not attributable
    </div>
  );
}

function PlayerRound({ caseData, given, onPlayAgain }: Props & { onPlayAgain: () => void }) {
  const slug = caseData.slug;
  const [state, dispatch] = useReducer(playerReducer, caseData, initPlayer);
  const saved = useSavedResult(slug);
  const submittedFrom = useRef<PlayerState | null>(null);
  const [revealPending, startReveal] = useTransition();
  const [revealError, setRevealError] = useState<string | null>(null);
  const headingId = useId();
  const revealedStages = useMemo(() => withheldStageKeys(caseData.stages), [caseData.stages]);
  const isDraft = caseData.review_status === "draft";

  const [submitState, submit, pending] = useActionState(async (_prev: SubmitState, formData: FormData): Promise<SubmitState> => {
    const next = await submitAttempt(slug, IDLE_SUBMIT, formData); // don't ship the previous state back to the server
    if (next.status === "done") saveResult(slug, next.result);
    else dispatch({ type: "closeFailed" }); // back to "playing": the button is enabled again for a retry
    return next;
  }, IDLE_SUBMIT);

  const result = saved ?? (submitState.status === "done" ? submitState.result : null);
  const submitError =
    submitState.status === "error"
      ? [submitState.message, ...Object.values(submitState.fieldErrors).flat()].filter(Boolean).join(" ")
      : null;
  const closing = state.phase === "closing" || pending;
  const announcement = result
    ? `Case closed. ${result.points} of ${result.max_points} points.`
    : closing
      ? "Closing the case."
      : (submitError ?? "");

  function lock(stage: PublicStage) {
    if (!canLock(state, stage)) return;
    dispatch({ type: "lock", stage: stage.key });
    if (!isRevealStage(stage.key)) return;
    const key = stage.key;
    const keys = state.selections[key] ?? [];
    setRevealError(null);
    startReveal(async () => {
      const res = await revealOptions(slug, key, keys);
      if (res.status === "ok") dispatch({ type: "revealed", stage: key, reveals: res.reveals });
      else setRevealError(res.message);
    });
  }

  function close() {
    // A second click that lands before React re-renders still sees the same `state` object:
    // remember which state was submitted and ignore repeats. After closeFailed the state changes,
    // so a deliberate retry goes through. Once re-rendered, closeRequest() returns null anyway.
    if (submittedFrom.current === state) return;
    const payload = closeRequest(state, Date.now());
    if (!payload) return;
    submittedFrom.current = state;
    dispatch({ type: "closeStarted" });
    startTransition(() => submit(attemptToFormData(payload)));
  }

  let body: ReactNode;
  if (result) {
    body = <DebriefView result={result} revealedStages={revealedStages} onPlayAgain={onPlayAgain} />;
  } else if (state.phase === "intro") {
    body = (
      <div className="mx-auto max-w-[640px] animate-rise">
        <CaseFileCard
          number={caseData.id}
          specialty={caseData.specialty}
          minutes={caseData.estimated_minutes}
          title={caseData.title}
          patient={caseData.patient}
          difficulty={caseData.difficulty}
          chiefComplaint={caseData.chief_complaint}
          hints={introHints(state.stages)}
          titleAs="h1"
          footer={
            <>
              <span>Nothing is marked until the case closes.</span>
              <Button variant="primary-sm" className="ml-auto" onClick={() => dispatch({ type: "start", at: Date.now() })}>
                Start case <ArrowIcon />
              </Button>
            </>
          }
        />
      </div>
    );
  } else {
    const stage = state.stages[state.current];
    const unlockedDecision = stage.kind === "decision" && !state.locked[stage.key];
    const isLast = state.current === state.stages.length - 1;
    const primary = unlockedDecision ? (
      <Button variant="primary-sm" disabled={!canLock(state, stage)} onClick={() => lock(stage)}>
        Lock in
      </Button>
    ) : isLast ? (
      <Button variant="primary-sm" disabled={closing || !canClose(state)} aria-busy={closing} onClick={close}>
        {closing ? "Closing…" : "Close the case"}
      </Button>
    ) : (
      <Button variant="primary-sm" disabled={!canAdvance(state)} onClick={() => dispatch({ type: "next" })}>
        Next stage
      </Button>
    );

    body = (
      <div className="grid gap-6 lg:grid-cols-[232px_minmax(0,1fr)] lg:gap-10">
        <StageRail state={state} onGo={(index) => dispatch({ type: "go", index })} />
        <div className="min-w-0">
          <p className="mb-3 font-mono text-[11px] text-muted">
            case {stageNo(caseData.id)} · stage {state.current + 1} of {state.stages.length}
          </p>
          <section aria-labelledby={headingId} className="overflow-hidden rounded-card border border-line bg-white shadow-lift">
            <header className="flex flex-wrap items-center gap-2.5 border-b border-line bg-surface-alt px-5 py-[13px]">
              <span className="font-mono text-eyebrow uppercase text-primary-hover">
                {stageNo(stage.number)} · {stage.label}
              </span>
              <MonoTag className="ml-auto">{stage.kind === "given" ? "given to you" : stage.hint}</MonoTag>
            </header>
            <div key={stage.key} className="animate-rise px-5 py-5 sm:px-6">
              {stage.kind === "given" ? (
                <>
                  <h2 id={headingId} className="sr-only">
                    {stage.label}
                  </h2>
                  {given[stage.key] ?? <p className="text-[14px] text-muted">Nothing recorded at this stage.</p>}
                </>
              ) : (
                <DecisionStage
                  stage={stage}
                  state={state}
                  dispatch={dispatch}
                  headingId={headingId}
                  revealPending={revealPending}
                  revealError={revealError}
                />
              )}
            </div>
            <footer className="flex flex-wrap items-center gap-3 border-t border-line bg-surface-alt px-5 py-3.5">
              <p className="font-mono text-[11px] text-muted">Nothing is marked until the case closes.</p>
              <div className="ml-auto flex gap-2">
                {state.current > 0 ? (
                  <Button variant="ghost-sm" disabled={closing} onClick={() => dispatch({ type: "back" })}>
                    Back
                  </Button>
                ) : null}
                {primary}
              </div>
            </footer>
          </section>
          {submitError && !closing ? (
            <p role="alert" className="mt-3 font-mono text-[12px] text-error">
              {submitError}
            </p>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <>
      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>
      {isDraft ? <DraftBanner /> : null}
      {body}
    </>
  );
}

type DecisionProps = {
  stage: PublicStage;
  state: PlayerState;
  dispatch: (action: PlayerAction) => void;
  headingId: string;
  revealPending: boolean;
  revealError: string | null;
};

function DecisionStage({ stage, state, dispatch, headingId, revealPending, revealError }: DecisionProps) {
  const locked = Boolean(state.locked[stage.key]);
  const frozen = locked || state.phase !== "playing";
  const options = stage.options ?? [];
  return (
    <div>
      <h2 id={headingId} className="text-h3 [overflow-wrap:anywhere]">
        {stage.prompt ?? stage.label}
      </h2>
      {stage.input === "free_text" ? (
        <div className="mt-5 space-y-6">
          <DiagnosisInput value={state.diagnosisText} disabled={frozen} onChange={(text) => dispatch({ type: "setDiagnosis", text })} />
          <ConfidenceSelector value={state.confidence} disabled={frozen} onChange={(value) => dispatch({ type: "setConfidence", value })} />
          {locked ? <p className="font-mono text-[11px] text-muted">Locked in.</p> : null}
        </div>
      ) : (
        <>
          <p className="mt-1.5 text-[13px] text-muted">{locked ? "Locked in." : "Choose all that apply, then lock in."}</p>
          <OptionChips
            label={stage.prompt ?? stage.label}
            options={options}
            selected={state.selections[stage.key] ?? []}
            disabled={frozen}
            onToggle={(key) => dispatch({ type: "toggle", stage: stage.key, key })}
          />
          {locked && isRevealStage(stage.key) ? (
            <RevealList stageKey={stage.key} options={options} reveals={state.reveals[stage.key]} pending={revealPending} error={revealError} />
          ) : null}
        </>
      )}
    </div>
  );
}
