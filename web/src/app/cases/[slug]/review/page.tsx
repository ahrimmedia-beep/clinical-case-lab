import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { cache } from "react";
import { ServiceUnavailable } from "@/components/case/service-unavailable";
import { AnswerKeyList, type KeyStage } from "@/components/review/answer-key";
import { ApproveForm } from "@/components/review/approve-form";
import { Checklist } from "@/components/review/checklist";
import { flaggedItems, hasFailures, reviewSummary } from "@/components/review/review";
import { buttonClasses } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Eyebrow } from "@/components/ui/eyebrow";
import { ArrowIcon } from "@/components/ui/icons";
import { MonoTag } from "@/components/ui/mono-tag";
import { getCaseReview, internalMessage, type CaseReview } from "@/lib/api/internal";
import { isValidSlug } from "@/lib/forms";
import { modelLabel } from "@/lib/format";

type Props = { params: Promise<{ slug: string }> };
type Loaded = { kind: "ok"; review: CaseReview } | { kind: "missing" } | { kind: "error"; message: string };

const loadReview = cache(async (slug: string): Promise<Loaded> => {
  if (!isValidSlug(slug)) return { kind: "missing" };
  try {
    const review = await getCaseReview(slug);
    return review ? { kind: "ok", review } : { kind: "missing" };
  } catch (error) {
    return { kind: "error", message: internalMessage(error) };
  }
});

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const loaded = await loadReview(slug);
  // Never indexed: a draft's review shows its answer key.
  return { title: loaded.kind === "ok" ? `Review · ${loaded.review.title}` : "Review", robots: { index: false, follow: false } };
}

function sourceLine(review: CaseReview): string {
  const s = review.source;
  if (s.kind !== "llm") return "Written by hand";
  const parts = [s.model ? `Drafted by ${modelLabel(s.model)}` : "Drafted by a model", s.prompt_version ? `prompt ${s.prompt_version}` : null];
  return parts.filter(Boolean).join(" · ");
}

export default async function ReviewPage({ params }: Props) {
  await connection();
  const { slug } = await params;
  const loaded = await loadReview(slug);
  if (loaded.kind === "missing") notFound();
  if (loaded.kind === "error") {
    return (
      <div className="mx-auto max-w-site px-4 py-16 sm:px-6">
        <ServiceUnavailable message={loaded.message} retryHref={`/cases/${slug}/review`} />
      </div>
    );
  }

  const { review } = loaded;

  // A live case keeps its answer key hidden: the key only appears in the debrief after the case closes.
  if (review.review_status === "approved") {
    return (
      <div className="mx-auto max-w-site px-4 py-[clamp(48px,7vw,96px)] sm:px-6">
        <div className="max-w-[620px] rounded-card border border-line bg-white p-6 shadow-card sm:p-8">
          <div className="flex flex-wrap items-center gap-2">
            <Eyebrow>Physician review</Eyebrow>
            <MonoTag tone="teal">Physician-reviewed</MonoTag>
          </div>
          <h1 className="mt-3 text-[clamp(23px,2.6vw,30px)] [overflow-wrap:anywhere]">{review.title}</h1>
          <p className="mt-3 text-[15px]">
            Approved by a reviewer. The case plays like any other in the catalogue, and its answer key stays hidden until you close it.
          </p>
          <Link href={`/cases/${review.slug}`} className={buttonClasses("primary", "mt-6")}>
            Play the case <ArrowIcon />
          </Link>
        </div>
      </div>
    );
  }

  const flagged = flaggedItems(review.checklist);
  const blocked = hasFailures(review.checklist);
  const key = review.answer_key;
  const stages: KeyStage[] = key.stages.map((s) => ({
    stage: s.stage,
    prompt: s.prompt,
    explanation: s.explanation,
    options: s.options ?? [],
    accepted: s.stage === "diagnosis" ? key.accepted_answers : undefined,
  }));

  return (
    <div className="mx-auto max-w-site px-4 py-[clamp(40px,6vw,80px)] sm:px-6">
      <header className="max-w-[760px]">
        <div className="flex flex-wrap items-center gap-2">
          <Eyebrow>Physician review</Eyebrow>
          <MonoTag tone="clay">AI draft · not physician-reviewed</MonoTag>
        </div>
        <h1 className="mt-3 text-[clamp(27px,3.1vw,38px)] [overflow-wrap:anywhere]">{review.title}</h1>
        <p className="mt-2 font-mono text-[11.5px] text-muted">{sourceLine(review)}</p>
        <p className="mt-5 text-lead text-ink">{reviewSummary(review.checklist)}</p>
        <p className="mt-2 text-[14px] text-muted">
          The checks below run on the server without a model: every quote is searched in the de-identified source, harmful options are listed
          for sign-off, and the visible text is scanned for the diagnosis and for identifiers.
        </p>
      </header>

      {/* DOM order checklist → answer key → sign-off, so on a phone the key is read before the button. */}
      <div className="mt-10 grid items-start gap-6 lg:grid-cols-[1fr_1.1fr] lg:grid-rows-[auto_1fr]">
        <Card className="lg:col-start-1 lg:row-start-1">
          <CardHeader title="Checklist" tag={flagged === 0 ? "nothing flagged" : `${flagged} flagged`} />
          <Checklist items={review.checklist} />
        </Card>

        <Card className="lg:col-start-2 lg:row-span-2 lg:row-start-1">
          <CardHeader title="Answer key" tag="reviewer view" />
          <div className="border-b border-line px-5 py-4">
            <p className="font-mono text-[10.5px] uppercase tracking-[.1em] text-muted">Final diagnosis</p>
            <p className="mt-1 text-[17px] font-semibold tracking-[-.015em] text-ink">
              {key.final_diagnosis.name}
              {key.final_diagnosis.icd10 ? <span className="ml-2 font-mono text-[12px] font-normal text-muted">{key.final_diagnosis.icd10}</span> : null}
            </p>
            {key.final_diagnosis.evidence ? (
              <p className="mt-1 text-[13px] text-muted">
                Source: <q className="text-body">{key.final_diagnosis.evidence}</q>
              </p>
            ) : null}
          </div>
          <AnswerKeyList stages={stages} finalDiagnosis={key.final_diagnosis.name} open="all" />
        </Card>

        <section aria-labelledby="signoff-title" className="rounded-card border border-line bg-surface-alt p-5 sm:p-6 lg:col-start-1 lg:row-start-2">
          <h2 id="signoff-title" className="text-[16px] tracking-[-.015em]">
            Sign-off
          </h2>
          <p className="mb-4 mt-1.5 text-[13.5px]">
            Approval moves the case to the physician-reviewed shelf and takes the draft banner off the player.
          </p>
          <ApproveForm slug={review.slug} flagged={flagged} blocked={blocked} />
        </section>
      </div>
    </div>
  );
}
