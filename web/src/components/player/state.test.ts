import { describe, expect, it } from "vitest";
import { peCasePublic, stressCasePublic } from "@/lib/api/fixtures";
import type { CasePublic } from "@/lib/api/types";
import { parseAttemptForm } from "@/lib/forms";
import {
  attemptToFormData,
  canClose,
  canLock,
  closeRequest,
  initPlayer,
  playerReducer,
  stageStatus,
  withheldStageKeys,
  type PlayerAction,
  type PlayerState,
} from "./state";

const T0 = 1_000;

function run(state: PlayerState, ...actions: PlayerAction[]): PlayerState {
  return actions.reduce(playerReducer, state);
}

function started(caseData: CasePublic = peCasePublic): PlayerState {
  return run(initPlayer(caseData), { type: "start", at: T0 });
}

/** Plays every stage: first option on multi-selects, "Pulmonary embolism" at confidence 4 on the diagnosis. */
function playToEnd(caseData: CasePublic = peCasePublic): PlayerState {
  let s = started(caseData);
  for (const stage of s.stages) {
    if (stage.kind === "decision") {
      s =
        stage.input === "free_text"
          ? run(s, { type: "setDiagnosis", text: "  Pulmonary embolism  " }, { type: "setConfidence", value: 4 })
          : run(s, { type: "toggle", stage: stage.key, key: (stage.options ?? [])[0].key });
      s = run(s, { type: "lock", stage: stage.key });
    }
    s = run(s, { type: "next" });
  }
  return s;
}

describe("player reducer", () => {
  it("starts on the intro with stages sorted by catalogue number", () => {
    const s = initPlayer({ stages: [...peCasePublic.stages].reverse() });
    expect(s.phase).toBe("intro");
    expect(s.stages.map((st) => st.number)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
  });

  it("ignores selections before the case starts and on given stages", () => {
    const intro = initPlayer(peCasePublic);
    expect(playerReducer(intro, { type: "toggle", stage: "interview", key: "A" })).toBe(intro);
    const s = started();
    expect(playerReducer(s, { type: "toggle", stage: "history", key: "A" })).toBe(s);
  });

  it("toggles options on and off and ignores unknown keys", () => {
    const s = run(started(), { type: "toggle", stage: "interview", key: "A" }, { type: "toggle", stage: "interview", key: "B" }, { type: "toggle", stage: "interview", key: "A" });
    expect(s.selections.interview).toEqual(["B"]);
    expect(playerReducer(s, { type: "toggle", stage: "interview", key: "Z" })).toBe(s);
  });

  it("blocks Next on an unlocked decision and allows it after Lock in", () => {
    let s = run(started(), { type: "next" }, { type: "next" });
    expect(s.stages[s.current].key).toBe("interview");
    expect(run(s, { type: "next" }).current).toBe(2);
    s = run(s, { type: "toggle", stage: "interview", key: "A" }, { type: "lock", stage: "interview" }, { type: "next" });
    expect(s.current).toBe(3);
    expect(s.visited).toBe(3);
  });

  it("needs a selection to lock, and freezes the stage once locked", () => {
    let s = run(started(), { type: "lock", stage: "interview" });
    expect(s.locked.interview).toBeUndefined();
    s = run(s, { type: "toggle", stage: "interview", key: "A" }, { type: "lock", stage: "interview" });
    expect(s.locked.interview).toBe(true);
    expect(playerReducer(s, { type: "toggle", stage: "interview", key: "B" })).toBe(s);
    expect(s.selections.interview).toEqual(["A"]);
  });

  it("needs both a diagnosis and a confidence to lock the diagnosis", () => {
    const diagnosis = peCasePublic.stages[7];
    let s: PlayerState = { ...started(), current: 7, visited: 7 };
    expect(canLock(s, diagnosis)).toBe(false);
    s = run(s, { type: "setDiagnosis", text: "Pulmonary embolism" }, { type: "setConfidence", value: 9 });
    expect(s.confidence).toBeNull();
    expect(canLock(s, diagnosis)).toBe(false);
    s = run(s, { type: "setConfidence", value: 3 }, { type: "lock", stage: "diagnosis" });
    expect(s.locked.diagnosis).toBe(true);
    expect(run(s, { type: "setDiagnosis", text: "Pneumonia" }).diagnosisText).toBe("Pulmonary embolism");
  });

  it("cannot jump ahead of the furthest visited stage", () => {
    let s = run(started(), { type: "go", index: 3 });
    expect(s.current).toBe(0);
    s = run(s, { type: "next" }, { type: "go", index: 0 });
    expect(s.current).toBe(0);
    expect(run(s, { type: "go", index: 1 }).current).toBe(1);
  });

  it("closes only when every decision is locked and builds the exact payload", () => {
    const s = playToEnd();
    expect(canClose(s)).toBe(true);
    expect(closeRequest(s, T0 + 61_000)).toEqual({
      choices: { interview: ["A"], differential: ["A"], workup: ["A"], treatment: ["A"] },
      diagnosis_text: "Pulmonary embolism",
      confidence: 4,
      duration_ms: 61_000,
    });
    const unlocked: PlayerState = { ...s, locked: { ...s.locked, workup: false } };
    expect(canClose(unlocked)).toBe(false);
    expect(closeRequest(unlocked, T0)).toBeNull();
  });

  it("refuses a second close while the first is in flight (double-click guard)", () => {
    const closing = run(playToEnd(), { type: "closeStarted" });
    expect(closing.phase).toBe("closing");
    expect(closeRequest(closing, T0)).toBeNull();
    expect(playerReducer(closing, { type: "closeStarted" })).toBe(closing);
    expect(playerReducer(closing, { type: "back" })).toBe(closing);
    const retry = run(closing, { type: "closeFailed" });
    expect(retry.phase).toBe("playing");
    expect(closeRequest(retry, T0)).not.toBeNull();
  });

  it("plays a case with missing stages, an empty given stage and a withheld result", () => {
    const s = playToEnd(stressCasePublic);
    expect(s.stages.map((st) => st.number)).toEqual([1, 2, 4, 5, 7, 8, 9]);
    expect(s.stages.find((st) => st.key === "examination")?.items).toEqual([]);
    expect(closeRequest(s, T0 + 5_000)?.choices).toEqual({ differential: ["A"], treatment: ["A"] });
    expect(withheldStageKeys(stressCasePublic.stages)).toEqual(new Set(["results"]));
    expect(withheldStageKeys(peCasePublic.stages).size).toBe(0);
  });

  it("round-trips the payload through FormData and the server-side parser", () => {
    const s = playToEnd();
    const payload = closeRequest({ ...s, selections: { ...s.selections, workup: ["C", "A"] } }, T0 + 61_000);
    if (!payload) throw new Error("expected a payload");
    expect(payload.choices?.workup).toEqual(["A", "C"]);
    expect(parseAttemptForm(attemptToFormData(payload))).toEqual({ ok: true, value: payload });
  });

  it("reports stage status for the rail", () => {
    let s = started();
    expect(stageStatus(s, 0)).toBe("current");
    expect(stageStatus(s, 1)).toBe("upcoming");
    s = run(s, { type: "next" }, { type: "next" });
    expect(stageStatus(s, 0)).toBe("done");
    expect(stageStatus(s, 2)).toBe("current");
    s = run(s, { type: "go", index: 0 });
    expect(stageStatus(s, 2)).toBe("open");
    s = run(s, { type: "go", index: 2 }, { type: "toggle", stage: "interview", key: "A" }, { type: "lock", stage: "interview" }, { type: "go", index: 0 });
    expect(stageStatus(s, 2)).toBe("done");
    expect(stageStatus(s, 1)).toBe("done");
  });
});
