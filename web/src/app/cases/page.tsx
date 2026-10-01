import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { CaseFileCard, type CaseFileHint } from "@/components/case/case-file-card";
import { ServiceUnavailable } from "@/components/case/service-unavailable";
import { Reveal } from "@/components/motion/reveal";
import { buttonClasses } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/eyebrow";
import { ArrowIcon } from "@/components/ui/icons";
import { listCases } from "@/lib/api/client";
import { friendlyMessage } from "@/lib/api/errors";
import type { CaseSummary } from "@/lib/api/types";
import { pluralize } from "@/lib/format";

export const metadata: Metadata = { title: "Cases" };

const HINTS: CaseFileHint[] = [
  { label: "Open the differential", hint: "your list" },
  { label: "Order the workup", hint: "your call" },
  { label: "Commit to a diagnosis", hint: "rate confidence" },
  { label: "Build the treatment plan", hint: "scored" },
];

type Loaded = { ok: true; cases: CaseSummary[] } | { ok: false; message: string };

async function load(): Promise<Loaded> {
  try {
    return { ok: true, cases: await listCases() };
  } catch (error) {
    return { ok: false, message: friendlyMessage(error) };
  }
}

/**
 * C1 delta (amendments §E): two shelves instead of one flat grid — "Physician-reviewed" cases
 * play for points attributable to the cohort; "AI drafts" are extracted but not yet checked by a
 * physician, so they get a Review link instead of pretending to be finished. Order within each
 * shelf is left exactly as the API/fixtures returned it (that is where "LAM first" — the hero
 * case the backend seeds first — comes from; this page never re-sorts).
 */
function CaseGrid({ cases, draft }: { cases: CaseSummary[]; draft: boolean }) {
  return (
    <ul className="grid gap-6 md:grid-cols-2">
      {cases.map((c) => (
        <li key={c.slug} data-reveal="">
          {/* Leans toward a mouse pointer; the shadow layer fades in instead of animating box-shadow. */}
          <div data-tilt="" className="relative h-full">
            <span aria-hidden="true" data-tilt-shadow="" className="pointer-events-none absolute inset-0 rounded-card opacity-0 shadow-lift" />
            <CaseFileCard
              number={c.id}
              specialty={c.specialty}
              minutes={c.estimated_minutes}
              title={c.title}
              patient={c.patient}
              difficulty={c.difficulty}
              chiefComplaint={c.chief_complaint}
              hints={HINTS}
              footer={
                draft ? (
                  <>
                    <span>AI-drafted · not yet checked</span>
                    <Link href={`/cases/${c.slug}/review`} className={buttonClasses("ghost-sm", "ml-auto")}>
                      Review
                    </Link>
                    <Link href={`/cases/${c.slug}`} className={buttonClasses("primary-sm")} aria-label={`Open case: ${c.title}`}>
                      Open case <ArrowIcon />
                    </Link>
                  </>
                ) : (
                  <>
                    <span>
                      {pluralize(c.attempts_count, "attempt")} · {c.source_kind === "llm" ? "LLM-authored" : "hand-written"}
                    </span>
                    <Link href={`/cases/${c.slug}`} className={buttonClasses("primary-sm", "ml-auto")} aria-label={`Open case: ${c.title}`}>
                      Open case <ArrowIcon />
                    </Link>
                  </>
                )
              }
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

export default async function CasesPage() {
  await connection();
  const loaded = await load();
  const approved = loaded.ok ? loaded.cases.filter((c) => c.review_status === "approved") : [];
  const drafts = loaded.ok ? loaded.cases.filter((c) => c.review_status === "draft") : [];

  return (
    <Reveal tilt className="mx-auto max-w-site px-4 py-[clamp(48px,7vw,96px)] sm:px-6">
      <header data-reveal="" className="mb-10 max-w-head">
        <Eyebrow>Case library</Eyebrow>
        <h1 className="mt-3 text-[clamp(27px,3.1vw,38px)]">Pick a patient</h1>
        <p className="mt-4 text-lead">
          Every case runs through the same nine stages. Nothing is marked until you close it; then the debrief shows each
          decision and where your result sits in the cohort.
        </p>
      </header>
      {!loaded.ok ? (
        <ServiceUnavailable message={loaded.message} retryHref="/cases" />
      ) : loaded.cases.length === 0 ? (
        <div className="max-w-[560px] rounded-card border border-line bg-surface-alt p-6">
          <h2 className="text-[19px]">No cases yet</h2>
          <p className="mt-2 text-[14px]">Turn a clinical note into the first one.</p>
          <Link href="/studio" className={buttonClasses("primary-sm", "mt-4")}>Open the studio</Link>
        </div>
      ) : (
        <div className="space-y-12">
          {approved.length > 0 ? (
            <section aria-labelledby="shelf-approved">
              <h2 id="shelf-approved" className="mb-4 font-mono text-[11.5px] font-medium uppercase tracking-[.1em] text-muted">
                Physician-reviewed
              </h2>
              <CaseGrid cases={approved} draft={false} />
            </section>
          ) : null}
          {drafts.length > 0 ? (
            <section aria-labelledby="shelf-draft">
              <h2 id="shelf-draft" className="mb-4 font-mono text-[11.5px] font-medium uppercase tracking-[.1em] text-muted">
                AI drafts · awaiting physician review
              </h2>
              <CaseGrid cases={drafts} draft={true} />
            </section>
          ) : null}
        </div>
      )}
    </Reveal>
  );
}
