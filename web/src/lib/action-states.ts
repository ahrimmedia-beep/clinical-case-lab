import type { AttemptResult, ExtractResponse, RevealOut } from "@/lib/api/types";

export type FieldErrors = Record<string, string[] | undefined>;

export type SubmitState =
  | { status: "idle" }
  | { status: "done"; result: AttemptResult }
  | { status: "error"; message: string; fieldErrors: FieldErrors };

export type ExtractState =
  | { status: "idle" }
  | { status: "done"; result: ExtractResponse }
  | { status: "error"; message: string; fieldErrors: FieldErrors };

export type PublishState = { status: "idle" } | { status: "error"; message: string };

export type RevealResult = { status: "ok"; reveals: RevealOut[] } | { status: "error"; message: string };

export const IDLE_SUBMIT: SubmitState = { status: "idle" };
export const IDLE_EXTRACT: ExtractState = { status: "idle" };
export const IDLE_PUBLISH: PublishState = { status: "idle" };
