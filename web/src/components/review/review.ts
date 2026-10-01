/** Pure helpers for the physician review page (★2). */

export type CheckStatus = "ok" | "warn" | "fail";
type CheckLike = { status: CheckStatus; items?: string[] };

/** "The reviewer checks N flagged items": every listed item on a warn/fail check (a check without items counts once). */
export function flaggedItems(checklist: readonly CheckLike[]): number {
  return checklist.filter((c) => c.status !== "ok").reduce((n, c) => n + Math.max(1, c.items?.length ?? 0), 0);
}

/** A failing check (a leak of the diagnosis, identifiers left in the source) blocks approval. */
export function hasFailures(checklist: readonly CheckLike[]): boolean {
  return checklist.some((c) => c.status === "fail");
}

export function reviewSummary(checklist: readonly CheckLike[]): string {
  const n = flaggedItems(checklist);
  return n === 0
    ? "AI-assisted, not AI-generated: nothing is flagged, so the reviewer confirms the answer key, not the whole case."
    : `AI-assisted, not AI-generated: the reviewer checks ${n} flagged ${n === 1 ? "item" : "items"}, not the whole case.`;
}

export type ApproveState = { status: "idle" } | { status: "error"; message: string };
export const IDLE_APPROVE: ApproveState = { status: "idle" };
