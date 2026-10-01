/** Friendly names for the generated OpenAPI types. Never edit schema.d.ts by hand: run `make gen`. */
import type { components } from "./schema";

export type { paths } from "./schema";

type Schemas = components["schemas"];

export type CasePublic = Schemas["CasePublic"];
export type PublicStage = Schemas["PublicStage"];
export type PublicOption = Schemas["PublicOption"];
export type StageItem = Schemas["StageItem"];
export type Patient = Schemas["Patient"];
export type CaseSummary = Schemas["CaseSummary"];
export type CaseCreated = Schemas["CaseCreated"];
export type ClinicalCase = Schemas["ClinicalCase"];
export type AttemptIn = Schemas["AttemptIn"];
export type AttemptResult = Schemas["AttemptResult"];
export type DebriefStage = Schemas["DebriefStage"];
export type DebriefOption = Schemas["DebriefOption"];
export type DiagnosisResult = Schemas["DiagnosisResult"];
export type HistogramBin = Schemas["HistogramBin"];
export type RevealIn = Schemas["RevealIn"];
export type RevealOut = Schemas["RevealOut"];
export type ExtractRequest = Schemas["ExtractRequest"];
export type ExtractResponse = Schemas["ExtractResponse"];
export type EvidenceSpan = Schemas["EvidenceSpan"];
export type PhiCount = Schemas["PhiCount"];
export type ProblemDetail = Schemas["ProblemDetail"];

// C1 delta (amendments §B/§E): review status on cases, AI benchmark markers, hedged diagnoses.
export type ReviewStatus = Schemas["ReviewStatus"];
export type Benchmark = Schemas["Benchmark"];

export type Stage = PublicStage["key"];
export type MultiSelectStage = Extract<Stage, "interview" | "differential" | "workup" | "treatment">;
export type RevealStage = RevealIn["stage"];
export type Provider = ExtractRequest["provider"];
export type OptionState = DebriefOption["state"];
export type Calibration = DiagnosisResult["calibration"];

export const MULTI_SELECT_STAGES = ["interview", "differential", "workup", "treatment"] as const satisfies readonly MultiSelectStage[];
export const REVEAL_STAGES = ["interview", "workup"] as const satisfies readonly RevealStage[];

export function isMultiSelectStage(key: Stage): key is MultiSelectStage {
  return (MULTI_SELECT_STAGES as readonly string[]).includes(key);
}

export function isRevealStage(key: Stage): key is RevealStage {
  return (REVEAL_STAGES as readonly string[]).includes(key);
}
