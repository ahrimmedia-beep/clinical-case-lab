"use server";

import { redirect } from "next/navigation";
import type { ApproveState } from "@/components/review/review";
import { approveCase as approve, internalMessage } from "@/lib/api/internal";
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
    if (outcome.status === "blocked") return { status: "error", message: outcome.message }; // the API re-ran the checklist
  } catch (error) {
    console.error("approveCase failed", { slug, error: String(error) });
    return { status: "error", message: internalMessage(error) };
  }
  redirect(`/cases/${slug}`); // outside try: redirect() works by throwing
}
