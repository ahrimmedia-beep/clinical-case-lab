import { afterEach, describe, expect, it, vi } from "vitest";
import { IDLE_APPROVE } from "@/components/review/review";
import { ApiError } from "@/lib/api/errors";
import { approveCase } from "./actions";

const redirect = vi.fn();
const approve = vi.fn();

vi.mock("next/navigation", () => ({ redirect: (path: string) => redirect(path) }));
vi.mock("@/lib/api/internal", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/internal")>()),
  approveCase: (slug: string) => approve(slug),
}));

const confirmed = () => {
  const fd = new FormData();
  fd.set("confirm", "on");
  return fd;
};

afterEach(() => {
  vi.restoreAllMocks();
  redirect.mockReset();
  approve.mockReset();
});

describe("approveCase", () => {
  it("approves a draft and opens the player", async () => {
    approve.mockResolvedValue({ status: "approved", result: { slug: "lam-draft-1a2b3c", review_status: "approved", reviewed_at: "2026-10-01T18:00:00Z" } });
    await approveCase("lam-draft-1a2b3c", IDLE_APPROVE, confirmed());
    expect(approve).toHaveBeenCalledWith("lam-draft-1a2b3c");
    expect(redirect).toHaveBeenCalledWith("/cases/lam-draft-1a2b3c");
  });

  it("treats an already approved case (409) as done and opens the player", async () => {
    approve.mockResolvedValue({ status: "already_approved" });
    await approveCase("lam-draft-1a2b3c", IDLE_APPROVE, confirmed());
    expect(redirect).toHaveBeenCalledWith("/cases/lam-draft-1a2b3c");
  });

  it("stays on the review with the API's reason when a check fails (409 from the server-side gate)", async () => {
    approve.mockResolvedValue({ status: "blocked", message: "Approval is blocked while a check fails: No identifiers in the source text." });
    expect(await approveCase("lam-draft-1a2b3c", IDLE_APPROVE, confirmed())).toEqual({
      status: "error",
      message: "Approval is blocked while a check fails: No identifiers in the source text.",
    });
    expect(redirect).not.toHaveBeenCalled();
  });

  it("needs the explicit sign-off and a valid slug before calling the API", async () => {
    expect(await approveCase("lam-draft-1a2b3c", IDLE_APPROVE, new FormData())).toEqual({
      status: "error",
      message: "Tick the box to confirm you checked the flagged items.",
    });
    expect(await approveCase("../admin", IDLE_APPROVE, confirmed())).toMatchObject({ status: "error", message: "This case link is not valid." });
    expect(approve).not.toHaveBeenCalled();
    expect(redirect).not.toHaveBeenCalled();
  });

  it("stays on the page with a calm message when the case is gone or the API fails", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    approve.mockResolvedValue({ status: "not_found" });
    expect(await approveCase("gone-case", IDLE_APPROVE, confirmed())).toMatchObject({ message: "This case doesn't exist, or it was removed." });
    approve.mockRejectedValue(new ApiError(503, "Unreachable"));
    expect(await approveCase("lam-draft-1a2b3c", IDLE_APPROVE, confirmed())).toMatchObject({ message: expect.stringContaining("can't reach") });
    approve.mockRejectedValue(new ApiError(401, "Unauthorized"));
    expect(await approveCase("lam-draft-1a2b3c", IDLE_APPROVE, confirmed())).toMatchObject({ message: "The case service didn't accept this server's key." });
    expect(redirect).not.toHaveBeenCalled();
  });
});
