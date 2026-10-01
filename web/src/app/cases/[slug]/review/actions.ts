"use server";

import { redirect } from "next/navigation";
import type { ApproveState } from "@/components/review/review";
import { ApiError, friendlyMessage } from "@/lib/api/errors";
import { approveCase as approve } from "@/lib/api/internal";
import { isValidSlug } from "@/lib/forms";

/**
 * Demo sign-off: one reviewer approves the draft (production would need two independent faculty
 * rounds). Already approved (409) is not an error: the reviewer lands on the player either way.
 */
export async function approveCase(slug: string, _prev: ApproveState, formData: FormData): Promise<ApproveState> {
  if (!isValidSlug(slug)) return { status: "error", message: "This case link is not valid." };
  if (formData.get("confirm") !== "on") {
    return { status: "error", message: "Tick the box to confirm you checked the flagged items." };
  }
  try {
    const outcome = await approve(slug);
    if (outcome.status === "not_found") return { status: "error", message: "This case doesn't exist, or it was removed." };
  } catch (error) {
    console.error("approveCase failed", { slug, error: String(error) });
    const keyProblem = error instanceof ApiError && (error.status === 401 || error.status === 403);
    return { status: "error", message: keyProblem ? "The case service didn't accept this server's key." : friendlyMessage(error) };
  }
  redirect(`/cases/${slug}`); // outside try: redirect() works by throwing
}
