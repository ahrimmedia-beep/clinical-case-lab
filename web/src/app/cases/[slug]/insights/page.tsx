import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { ServiceUnavailable } from "@/components/case/service-unavailable";
import { DecisionBars } from "@/components/insights/decision-bars";
import { biggestMiss, closedCookieName, pct } from "@/components/insights/insights";
import { KeyTest } from "@/components/insights/key-test";
import { Reveal } from "@/components/motion/reveal";
import { AiBenchmarks, WrongDiagnoses } from "@/components/insights/side-cards";
import { buttonClasses } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Eyebrow } from "@/components/ui/eyebrow";
import { ArrowIcon } from "@/components/ui/icons";
import { MonoTag } from "@/components/ui/mono-tag";
import { getCaseInsights, internalMessage, type CaseInsights } from "@/lib/api/internal";
import { verifyClosedCookie } from "@/lib/closed-cookie";
import { isValidSlug } from "@/lib/forms";
import { formatInt } from "@/lib/format";

type Props = { params: Promise<{ slug: string }> };

export const metadata: Metadata = { title: "Sponsor view", robots: { index: false, follow: false } };

function ClosedFirst({ slug }: { slug: string }) {
  return (
    <div className="mx-auto max-w-site px-4 py-[clamp(48px,7vw,96px)] sm:px-6">
      <div className="max-w-[620px] rounded-card border border-line bg-white p-6 shadow-card sm:p-8">
        <Eyebrow>Sponsor view</Eyebrow>
        <h1 className="mt-3 text-[clamp(23px,2.6vw,30px)]">Close the case first to see the sponsor view</h1>
        <p className="mt-3 text-[15px]">
          This page shows how the cohort decided at every fork of the case, including which answers were right. It opens once you have made
          your own calls and closed the case in this browser.
        </p>
        <Link href={`/cases/${slug}`} className={buttonClasses("primary", "mt-6")}>
          Play the case <ArrowIcon />
        </Link>
      </div>
    </div>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="px-5 py-5 sm:px-6">
      <dt className="font-mono text-[10.5px] uppercase tracking-[.1em] text-muted">{label}</dt>
      <dd data-count="" className="mt-1.5 text-[clamp(26px,3.4vw,36px)] font-semibold leading-none tracking-[-.03em] text-ink tabular-nums">
        {value}
      </dd>
      <dd className="mt-2 text-[13px] leading-snug text-body [overflow-wrap:anywhere]">{note}</dd>
    </div>
  );
}

export default async function InsightsPage({ params }: Props) {
  await connection();
  const { slug } = await params;
  if (!isValidSlug(slug)) notFound();
  // Gate: the signed httpOnly cookie set by the player's submitAttempt. Answers are shown below, so no valid
  // cookie (missing, hand-made, or copied from another case), no data.
  const closed = (await cookies()).get(closedCookieName(slug))?.value;
  if (!verifyClosedCookie(slug, closed)) return <ClosedFirst slug={slug} />;

  let insights: CaseInsights | null;
  try {
    insights = await getCaseInsights(slug);
  } catch (error) {
    return (
      <div className="mx-auto max-w-site px-4 py-16 sm:px-6">
        <ServiceUnavailable message={internalMessage(error)} retryHref={`/cases/${slug}/insights`} />
      </div>
    );
  }
  if (!insights) notFound();

  const stages = insights.stages ?? [];
  const miss = biggestMiss(stages);
  const accuracy = insights.diagnosis_accuracy ?? null;
  const empty = insights.cohort_size === 0;

  return (
    <Reveal className="mx-auto max-w-site px-4 py-[clamp(40px,6vw,80px)] sm:px-6">
      <header data-reveal="" className="max-w-[760px]">
        <div className="flex flex-wrap items-center gap-2">
          <Eyebrow>Sponsor view</Eyebrow>
          {insights.cohort_is_simulated ? <MonoTag tone="clay">simulated cohort</MonoTag> : null}
          <MonoTag>aggregates only</MonoTag>
        </div>
        <h1 className="mt-3 text-[clamp(27px,3.1vw,38px)] [overflow-wrap:anywhere]">{insights.title}</h1>
        <p className="mt-4 text-lead">
          Where the cohort went at every decision point: which right steps they skipped, which wrong calls they made, and which test changed
          the outcome. This is what a sponsor learns from a case, without a single name attached.
        </p>
      </header>

      {empty ? (
        <p data-reveal="" className="mt-10 max-w-[620px] rounded-card border border-line bg-surface-alt px-5 py-4 text-[14.5px]">
          No attempts are recorded for this case yet. The bars fill in as physicians close it.
        </p>
      ) : null}

      <dl data-reveal="" className="mt-10 grid divide-y divide-line overflow-hidden rounded-card border border-line bg-white shadow-card md:grid-cols-3 md:divide-x md:divide-y-0">
        <Stat
          label="Cohort"
          value={formatInt(insights.cohort_size)}
          note={insights.cohort_is_simulated ? "attempts, including a seeded simulated cohort" : "attempts by physicians"}
        />
        <Stat label="Right diagnosis" value={pct(accuracy)} note="named the accepted diagnosis, one candidate only" />
        <Stat
          label="Most missed step"
          value={miss ? pct(miss.missedRate) : "—"}
          note={miss ? `skipped “${miss.text}” (${miss.label.toLowerCase()})` : "nothing missed yet"}
        />
      </dl>

      {(insights.key_tests ?? []).length > 0 ? (
        <div data-reveal="" className="mt-8">
          <KeyTest tests={insights.key_tests ?? []} />
        </div>
      ) : null}

      <section aria-labelledby="forks-title" className="mt-14">
        <h2 id="forks-title" data-reveal="" className="text-[clamp(23px,2.6vw,30px)]">
          Decision points
        </h2>
        <p data-reveal="" className="mt-2 max-w-[620px] text-[14.5px]">
          Share of the cohort that picked each option. Correct options carry a ✓ and show how many physicians missed them; harmful options are
          marked in clay.
        </p>
        <div className="mt-6 grid items-start gap-6 md:grid-cols-2">
          {stages.map((stage) => (
            <DecisionBars key={stage.stage} stage={stage} />
          ))}
        </div>
      </section>

      <div className="mt-14 grid items-start gap-6 lg:grid-cols-2">
        <WrongDiagnoses items={insights.top_wrong_diagnoses ?? []} cohortSize={insights.cohort_size} accuracy={accuracy} />
        <AiBenchmarks items={insights.benchmarks ?? []} />
      </div>

      <Callout data-reveal="" className="mt-14" title="Nothing here is attributable to a physician.">
        Every figure is a share of the cohort. Individual attempts, names and scores never leave the server, and AI players are listed apart
        from the people.
      </Callout>
    </Reveal>
  );
}
