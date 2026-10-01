"use client";

import { useActionState, useId } from "react";
import { approveCase } from "@/app/cases/[slug]/review/actions";
import { Button } from "@/components/ui/button";
import { IDLE_APPROVE } from "./review";

type Props = { slug: string; flagged: number; blocked: boolean };

/** Explicit sign-off: a checkbox naming what was checked, then one demo approval round. */
export function ApproveForm({ slug, flagged, blocked }: Props) {
  const [state, action, pending] = useActionState(approveCase.bind(null, slug), IDLE_APPROVE);
  const confirmId = useId();
  const what = flagged === 0 ? "the answer key" : `the ${flagged} flagged ${flagged === 1 ? "item" : "items"} and the answer key`;

  return (
    <form action={action} className="space-y-4">
      {blocked ? (
        <p role="alert" className="rounded-[8px] border border-wrong-border bg-wrong-tint px-3 py-2.5 text-[13.5px] text-ink">
          A failing check blocks approval. Re-extract the note in the studio, or fix the case at its source.
        </p>
      ) : null}
      <label htmlFor={confirmId} className="flex cursor-pointer items-start gap-3 text-[14px] text-ink">
        <input
          id={confirmId}
          type="checkbox"
          name="confirm"
          required
          disabled={blocked}
          className="mt-0.5 size-[18px] flex-none cursor-pointer accent-[var(--color-primary)]"
        />
        <span>I checked {what}. The pathway is right and every harmful option is truly harmful.</span>
      </label>
      <Button type="submit" disabled={blocked || pending} aria-busy={pending} className="w-full flex-col gap-0.5 text-center sm:w-auto sm:items-start sm:text-left">
        <span>{pending ? "Approving…" : "Approve as reviewer"}</span>
        <span className="text-[11.5px] font-normal text-white/85">(demo — production needs two independent faculty rounds)</span>
      </Button>
      {state.status === "error" ? (
        <p role="alert" className="font-mono text-[12px] text-error">
          {state.message}
        </p>
      ) : null}
    </form>
  );
}
