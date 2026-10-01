import type { AttemptIn, CasePublic, PublicStage, RevealOut, Stage } from "@/lib/api/types";
import { isMultiSelectStage } from "@/lib/api/types";

/*
 * Everything the player decides lives here, as pure functions, so the rules that matter
 * (no skipping an unlocked decision, one close at a time, the exact payload) are unit-tested.
 * There is no notion of right or wrong in this file: correctness only exists in AttemptResult.
 */

export const DIAGNOSIS_MAX = 200;

export type Phase = "intro" | "playing" | "closing";

export interface PlayerState {
  stages: PublicStage[];
  phase: Phase;
  current: number;
  visited: number;
  selections: Partial<Record<Stage, string[]>>;
  locked: Partial<Record<Stage, boolean>>;
  reveals: Partial<Record<Stage, RevealOut[]>>;
  diagnosisText: string;
  confidence: number | null;
  startedAt: number | null;
}

export type PlayerAction =
  | { type: "start"; at: number }
  | { type: "go"; index: number }
  | { type: "next" }
  | { type: "back" }
  | { type: "toggle"; stage: Stage; key: string }
  | { type: "setDiagnosis"; text: string }
  | { type: "setConfidence"; value: number }
  | { type: "lock"; stage: Stage }
  | { type: "revealed"; stage: Stage; reveals: RevealOut[] }
  | { type: "closeStarted" }
  | { type: "closeFailed" };

export function initPlayer(caseData: Pick<CasePublic, "stages">): PlayerState {
  return {
    stages: [...caseData.stages].sort((a, b) => a.number - b.number),
    phase: "intro",
    current: 0,
    visited: 0,
    selections: {},
    locked: {},
    reveals: {},
    diagnosisText: "",
    confidence: null,
    startedAt: null,
  };
}

function stageByKey(state: PlayerState, key: Stage): PublicStage | undefined {
  return state.stages.find((s) => s.key === key);
}

export function canLock(state: PlayerState, stage: PublicStage): boolean {
  if (state.phase !== "playing" || stage.kind !== "decision" || state.locked[stage.key]) return false;
  if (stage.input === "free_text") return state.diagnosisText.trim().length > 0 && state.confidence !== null;
  return (state.selections[stage.key]?.length ?? 0) > 0;
}

export function canAdvance(state: PlayerState): boolean {
  const stage = state.stages[state.current];
  if (!stage || state.current >= state.stages.length - 1) return false;
  return stage.kind === "given" || Boolean(state.locked[stage.key]);
}

export function canClose(state: PlayerState): boolean {
  return state.phase === "playing" && state.stages.filter((s) => s.kind === "decision").every((s) => state.locked[s.key]);
}

export function playerReducer(state: PlayerState, action: PlayerAction): PlayerState {
  switch (action.type) {
    case "start":
      return state.phase === "intro" ? { ...state, phase: "playing", startedAt: action.at, current: 0, visited: 0 } : state;
    case "go":
      if (state.phase !== "playing" || action.index < 0 || action.index > state.visited || action.index === state.current) return state;
      return { ...state, current: action.index };
    case "next":
      if (state.phase !== "playing" || !canAdvance(state)) return state;
      return { ...state, current: state.current + 1, visited: Math.max(state.visited, state.current + 1) };
    case "back":
      if (state.phase !== "playing" || state.current === 0) return state;
      return { ...state, current: state.current - 1 };
    case "toggle": {
      const stage = stageByKey(state, action.stage);
      if (state.phase !== "playing" || !stage || stage.input !== "multi_select" || state.locked[stage.key]) return state;
      if (!(stage.options ?? []).some((o) => o.key === action.key)) return state;
      const chosen = state.selections[stage.key] ?? [];
      const next = chosen.includes(action.key) ? chosen.filter((k) => k !== action.key) : [...chosen, action.key];
      return { ...state, selections: { ...state.selections, [stage.key]: next } };
    }
    case "setDiagnosis":
      if (state.phase !== "playing" || state.locked.diagnosis) return state;
      return { ...state, diagnosisText: action.text.slice(0, DIAGNOSIS_MAX) };
    case "setConfidence":
      if (state.phase !== "playing" || state.locked.diagnosis) return state;
      if (!Number.isInteger(action.value) || action.value < 1 || action.value > 5) return state;
      return { ...state, confidence: action.value };
    case "lock": {
      const stage = stageByKey(state, action.stage);
      if (!stage || !canLock(state, stage)) return state;
      return { ...state, locked: { ...state.locked, [stage.key]: true } };
    }
    case "revealed":
      return { ...state, reveals: { ...state.reveals, [action.stage]: action.reveals } };
    case "closeStarted":
      return canClose(state) ? { ...state, phase: "closing" } : state;
    case "closeFailed":
      return state.phase === "closing" ? { ...state, phase: "playing" } : state;
  }
}

export function buildAttemptPayload(state: PlayerState, now: number): AttemptIn {
  const choices: AttemptIn["choices"] = {};
  for (const stage of state.stages) {
    if (stage.input !== "multi_select" || !isMultiSelectStage(stage.key)) continue;
    const keys = state.selections[stage.key] ?? [];
    if (keys.length > 0) choices[stage.key] = [...keys].sort();
  }
  return {
    choices,
    diagnosis_text: state.diagnosisText.trim(),
    confidence: state.confidence ?? 1,
    duration_ms: state.startedAt === null ? null : Math.min(3_600_000, Math.max(0, Math.round(now - state.startedAt))),
  };
}

/** The single gate in front of submitAttempt: null unless every decision is locked and no close is in flight. */
export function closeRequest(state: PlayerState, now: number): AttemptIn | null {
  return canClose(state) ? buildAttemptPayload(state, now) : null;
}

export function attemptToFormData(payload: AttemptIn): FormData {
  const fd = new FormData();
  fd.set("choices", JSON.stringify(payload.choices));
  fd.set("diagnosis_text", payload.diagnosis_text);
  fd.set("confidence", String(payload.confidence));
  if (payload.duration_ms !== null && payload.duration_ms !== undefined) fd.set("duration_ms", String(payload.duration_ms));
  return fd;
}

export type StageStatus = "current" | "done" | "open" | "upcoming";

export function stageStatus(state: PlayerState, index: number): StageStatus {
  if (index === state.current) return "current";
  const stage = state.stages[index];
  if (stage.kind === "decision" && state.locked[stage.key]) return "done";
  if (stage.kind === "given" && index < state.visited) return "done";
  return index <= state.visited ? "open" : "upcoming";
}

/** Given stages that hid an item during play ("Result withheld until the debrief"). */
export function withheldStageKeys(stages: PublicStage[]): Set<string> {
  return new Set(stages.filter((s) => (s.items ?? []).some((item) => item.withheld)).map((s) => s.key));
}
