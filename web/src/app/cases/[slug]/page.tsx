import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { cache } from "react";
import { GivenStage } from "@/components/case/given-stage";
import { ServiceUnavailable } from "@/components/case/service-unavailable";
import { CasePlayer, type GivenSlots } from "@/components/player/case-player";
import { getCase } from "@/lib/api/client";
import { friendlyMessage } from "@/lib/api/errors";
import type { CasePublic } from "@/lib/api/types";
import { isValidSlug } from "@/lib/forms";

// Next 16: params is a Promise.
type Props = { params: Promise<{ slug: string }> };

type Loaded = { kind: "ok"; caseData: CasePublic } | { kind: "missing" } | { kind: "error"; message: string };

// Deduplicates the fetch between generateMetadata and the page within one request.
const loadCase = cache(async (slug: string): Promise<Loaded> => {
  if (!isValidSlug(slug)) return { kind: "missing" };
  try {
    const caseData = await getCase(slug);
    return caseData ? { kind: "ok", caseData } : { kind: "missing" };
  } catch (error) {
    return { kind: "error", message: friendlyMessage(error) };
  }
});

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const loaded = await loadCase(slug);
  return { title: loaded.kind === "ok" ? loaded.caseData.title : "Case" };
}

export default async function CasePage({ params }: Props) {
  await connection();
  const { slug } = await params;
  const loaded = await loadCase(slug);
  if (loaded.kind === "missing") notFound();
  if (loaded.kind === "error") {
    return (
      <div className="mx-auto max-w-site px-4 py-16 sm:px-6">
        <ServiceUnavailable message={loaded.message} retryHref={`/cases/${slug}`} />
      </div>
    );
  }

  const { caseData } = loaded;
  // Server Components rendered here and handed to the client stepper as props.
  const given: GivenSlots = {};
  for (const stage of caseData.stages) {
    if (stage.kind === "given") given[stage.key] = <GivenStage stage={stage} caseData={caseData} />;
  }

  return (
    <div className="mx-auto max-w-site px-4 py-[clamp(32px,5vw,64px)] sm:px-6">
      <CasePlayer caseData={caseData} given={given} />
    </div>
  );
}
