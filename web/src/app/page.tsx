import Link from "next/link";
import { connection } from "next/server";
import { pickHeroCase } from "@/components/landing/hero";
import { HeroCase } from "@/components/landing/hero-case";
import { FlowMotion } from "@/components/motion/flow-motion";
import { HeroMotion } from "@/components/motion/hero-motion";
import { Reveal } from "@/components/motion/reveal";
import { buttonClasses } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Eyebrow } from "@/components/ui/eyebrow";
import { ArrowIcon } from "@/components/ui/icons";
import { MonoTag } from "@/components/ui/mono-tag";
import { Pill } from "@/components/ui/pill";
import { listCases } from "@/lib/api/client";
import type { CaseSummary } from "@/lib/api/types";
import { apiDocsUrl } from "@/lib/env";
import { compareModels, headline, loadEvalReport, type Headline } from "@/lib/evals";
import { stageNo } from "@/lib/format";
import { GITHUB_URL } from "@/lib/links";

type CardLink = { href: string; label: string; external?: boolean };
type InfoCard = { kicker: string; title: string; body: string; points?: string[]; links: CardLink[] };

const FLOW = [
  ["Raw note", "pasted or sampled"],
  ["De-identify", "names, dates, IDs masked"],
  ["Extract and ground", "every fact quoted, every quote checked"],
  ["Physician review", "flagged items, not the whole case"],
  ["Play", "nine stages, scored on the server"],
  ["Debrief", "percentile, AI markers, sponsor view"],
] as const;

function TextLink({ link }: { link: CardLink }) {
  const content = (
    <>
      {link.label} <ArrowIcon />
    </>
  );
  return link.external ? (
    <a href={link.href} target="_blank" rel="noreferrer" className={buttonClasses("link")}>
      {content}
    </a>
  ) : (
    <Link href={link.href} className={buttonClasses("link")}>
      {content}
    </Link>
  );
}

function EvalStats({ stats, onDark = false }: { stats: Headline | null; onDark?: boolean }) {
  return (
    <div className={onDark ? "rounded-hero-card bg-white p-6 text-body shadow-on-dark sm:p-7" : "rounded-card border border-line bg-white p-6 shadow-card sm:p-7"}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-[16px] tracking-[-.015em]">Extraction accuracy</h3>
        <MonoTag tone={stats?.sample ? "clay" : "neutral"}>{stats?.sample ? "Sample figures" : "8-case gold set"}</MonoTag>
      </div>
      {stats ? (
        <>
          <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-5">
            {[
              ["Macro-F1", stats.macroF1],
              ["Quotes found", stats.grounded],
              ["Hallucinated", stats.hallucination],
              ["Cost per case", stats.cost],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="font-mono text-[10.5px] uppercase tracking-[.1em] text-muted">{label}</dt>
                <dd data-count="" className="mt-1 text-[clamp(28px,3vw,34px)] font-semibold leading-none tracking-[-.03em] text-ink tabular-nums">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-5 border-t border-line pt-3 text-[12.5px] text-muted">
            {stats.model}, best of {stats.models} models on the same notes.{" "}
            <Link href="/evals" className="font-medium text-primary-hover hover:underline">
              Full comparison
            </Link>
          </p>
        </>
      ) : (
        <p className="mt-5 text-[14px]">
          The model comparison appears after the first eval run.{" "}
          <Link href="/evals" className="font-medium text-primary-hover hover:underline">
            Eval page
          </Link>
        </p>
      )}
    </div>
  );
}

async function loadCases(): Promise<CaseSummary[]> {
  try {
    return await listCases();
  } catch {
    return []; // the landing never fails because the API is down: the hero falls back to the eval card
  }
}

export default async function HomePage() {
  await connection();
  const loaded = loadEvalReport();
  const stats = loaded.ok ? headline(loaded.report) : null;
  const migration = loaded.ok ? compareModels(loaded.report, "claude-opus-4-8", "claude-opus-5-5") : null;
  const picked = pickHeroCase(await loadCases());
  const heroHref = picked ? `/cases/${picked.hero.slug}` : "/cases";
  const docs = apiDocsUrl();

  const tasks: InfoCard[] = [
    {
      kicker: "Backend",
      title: "FastAPI and PostgreSQL",
      body: "Cases arrive as JSON, land in a normalized schema through Alembic migrations, and every attempt is scored on the server.",
      points: [
        "Idempotent ingest keyed by a content hash",
        "Answers never reach the browser before the case closes",
        "Select-all and hedged diagnoses earn nothing",
      ],
      links: [...(docs ? [{ href: docs, label: "API docs", external: true }] : []), { href: "/cases", label: "Browse cases" }],
    },
    {
      kicker: "Frontend",
      title: "Next.js App Router",
      body: "Server Components render the case, a client stepper plays it, and a Server Action submits the answers. Types come from the API's OpenAPI schema.",
      points: [
        "Given stages are server-rendered and slotted into the client player",
        "The debrief marks every decision right, wrong or missed",
        "One generated types file behind every API call",
      ],
      links: [{ href: heroHref, label: "Play a case" }],
    },
    {
      kicker: "LLM pipeline",
      title: "Gemini and Claude on Vertex AI",
      body: "Text is de-identified, extracted against a JSON schema with a verbatim quote for every fact, checked against the source, then authored into decisions.",
      points: [
        "Validate-and-repair loop on schema errors",
        "Every quote verified against the source text",
        "Eval harness: accuracy per field, hallucinations, latency, cost",
      ],
      links: [
        { href: "/studio", label: "Open the studio" },
        { href: "/evals", label: "See the evals" },
      ],
    },
  ];

  const extras: InfoCard[] = [
    {
      kicker: "AI players",
      title: "Models on the same curve as physicians",
      body: "Gemini and Claude play every showcase case blinded, through the same scoring code. They show up as labelled markers on your percentile curve and never enter the cohort.",
      links: [{ href: heroHref, label: "Play, then see the curve" }],
    },
    {
      kicker: "Review gate",
      title: "AI-assisted, not AI-generated",
      body: "Studio output is only a draft. A reviewer sees the answer key and a server-computed checklist, checks the few flagged items, and signs off before the case counts.",
      links: [{ href: "/studio", label: "Draft a case in the studio" }],
    },
    {
      kicker: "Sponsor view",
      title: "Where the cohort turned",
      body: "After you close a case: pick rates at every decision point, the right steps most physicians skipped, and how ordering the key test changed the diagnosis rate.",
      links: [{ href: heroHref, label: "Close a case to open it" }],
    },
  ];

  return (
    <>
      <HeroMotion
        copy={
          <>
            <div data-intro="lead">
              <Pill tone="dark">
                <span aria-hidden="true" className="size-[7px] rounded-full bg-primary-lit" />
                Take-home · three tasks, one flow
              </Pill>
            </div>
            <h1 data-intro="title" data-split="" className="mt-6 text-[clamp(31px,4.2vw,54px)] leading-[1.04] tracking-[-.036em] text-white">
              Clinical cases, end to end
            </h1>
            <p data-intro="copy" className="mt-5 max-w-[540px] text-lead text-hero-text/80">
              A clinical note becomes a structured case with a verbatim source quote behind every fact. A physician reviews the AI draft, peers
              play it stage by stage, and the server scores every decision, opens the debrief and shows where the cohort turned.
            </p>
            {picked?.isRareDiseaseHero ? (
              <p data-intro="copy" className="mt-4 max-w-[540px] text-[14.5px] text-hero-text/70">
                Rare diseases take years to diagnose because the first explanation usually fits well enough. The featured case is built to test
                the second look.
              </p>
            ) : null}
            <div data-intro="copy" className="mt-8 flex flex-wrap gap-3">
              <Link href={heroHref} className={buttonClasses("on-dark")}>
                {picked?.isRareDiseaseHero ? "Play the case most physicians miss" : "Play a case"} <ArrowIcon />
              </Link>
              <Link href="/studio" className={buttonClasses("on-dark-ghost")}>
                Turn a note into a case
              </Link>
            </div>
            <p data-intro="copy" className="mt-6 font-mono text-[11.5px] text-hero-text/60">
              FastAPI · PostgreSQL 18 · Next.js 16 · Gemini and Claude on Vertex AI · Cloud Run
            </p>
          </>
        }
        aside={picked ? <HeroCase hero={picked.hero} isRareDiseaseHero={picked.isRareDiseaseHero} /> : <EvalStats stats={stats} onDark />}
      />

      <Reveal>
        <section className="py-[clamp(72px,9vw,120px)]">
          <div className="mx-auto max-w-site px-4 sm:px-6">
            <div data-reveal="" className="mb-[clamp(36px,5vw,56px)] max-w-head">
              <Eyebrow>The take-home</Eyebrow>
              <h2 className="mt-3.5 text-[clamp(27px,3.1vw,38px)]">Three tasks, wired into one product</h2>
              <p className="mt-4 max-w-[560px] text-lead">Each part runs live. Open a card to see it working.</p>
            </div>
            <ul className="grid gap-6 md:grid-cols-3">
              {tasks.map((task, i) => (
                <li
                  key={task.kicker}
                  data-reveal=""
                  className="relative flex flex-col overflow-hidden rounded-card border border-line bg-white p-6 shadow-card before:absolute before:inset-x-0 before:top-0 before:h-1 before:bg-brand-grad"
                >
                  <span className="flex items-center gap-2.5">
                    <span className="flex h-6 min-w-6 items-center justify-center rounded-badge border border-primary-border bg-primary-tint px-1.5 font-mono text-[11px] text-primary-hover">
                      {stageNo(i + 1)}
                    </span>
                    <span className="font-mono text-eyebrow uppercase text-primary-hover">{task.kicker}</span>
                  </span>
                  <h3 className="mt-4 text-h3">{task.title}</h3>
                  <p className="mt-2 text-[14.5px]">{task.body}</p>
                  <ul className="mt-4 space-y-1.5 text-[13.5px]">
                    {(task.points ?? []).map((point) => (
                      <li key={point} className="flex gap-2">
                        <span aria-hidden="true" className="mt-[9px] size-[5px] flex-none rounded-full bg-primary" />
                        {point}
                      </li>
                    ))}
                  </ul>
                  <div className="mt-auto flex flex-wrap gap-x-5 gap-y-2 pt-6">
                    {task.links.map((link) => (
                      <TextLink key={link.href + link.label} link={link} />
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="border-y border-line bg-surface-alt py-[clamp(64px,8vw,104px)]">
          <div className="mx-auto max-w-site px-4 sm:px-6">
            <div data-reveal="" className="mb-10 max-w-head">
              <Eyebrow>The flow</Eyebrow>
              <h2 className="mt-3.5 text-[clamp(27px,3.1vw,38px)]">From a note to a debrief</h2>
            </div>
            <FlowMotion className="relative">
              {/* The rail: a horizontal line through the step nodes from 1024 px, a vertical one below 640 px. */}
              <span aria-hidden="true" className="pointer-events-none absolute inset-x-[calc((100%_-_60px)/12)] top-[14px] hidden h-px bg-line-strong lg:block" />
              <span
                aria-hidden="true"
                data-flow-line="x"
                className="pointer-events-none absolute inset-x-[calc((100%_-_60px)/12)] top-[13px] hidden h-[3px] rounded-full bg-primary lg:block"
              />
              <span aria-hidden="true" className="pointer-events-none absolute bottom-12 left-[6px] top-12 w-px bg-line-strong sm:hidden" />
              <span
                aria-hidden="true"
                data-flow-line="y"
                className="pointer-events-none absolute bottom-12 left-[5px] top-12 w-[3px] rounded-full bg-primary sm:hidden"
              />
              <ol className="grid gap-3 pl-7 sm:grid-cols-3 sm:pl-0 lg:grid-cols-6 lg:pt-9">
                {FLOW.map(([title, hint], i) => (
                  <li key={title} data-flow-step="" className="relative rounded-tile border border-line bg-white px-4 py-3.5">
                    <span
                      aria-hidden="true"
                      data-flow-node=""
                      className="absolute -left-[28px] top-[calc(50%_-_6px)] size-3 rounded-full border-2 border-primary bg-surface-alt sm:hidden lg:left-[calc(50%_-_6px)] lg:top-[-28px] lg:block"
                    />
                    <span className="font-mono text-[10.5px] text-muted">{stageNo(i + 1)}</span>
                    <p className="mt-1 text-[14.5px] font-medium text-ink">{title}</p>
                    <p className="text-[12.5px] text-muted">{hint}</p>
                  </li>
                ))}
              </ol>
            </FlowMotion>
            <Callout data-reveal="" className="mt-10" title="Nothing is marked until the case closes.">
              The player never shows right or wrong mid-case, and the answers stay on the server until you submit. Points come only from the
              diagnosis and the treatment plan.
            </Callout>
          </div>
        </section>

        <section className="py-[clamp(72px,9vw,120px)]">
          <div className="mx-auto max-w-site px-4 sm:px-6">
            <div data-reveal="" className="mb-[clamp(36px,5vw,56px)] max-w-head">
              <Eyebrow>What else is here</Eyebrow>
              <h2 className="mt-3.5 text-[clamp(27px,3.1vw,38px)]">Three things beyond the brief</h2>
              <p className="mt-4 max-w-[560px] text-lead">Built after the three tasks were done and tested, around how a case platform actually runs.</p>
            </div>
            <ul className="grid gap-6 md:grid-cols-3">
              {extras.map((card) => (
                <li key={card.kicker} data-reveal="" className="flex flex-col rounded-card border border-line bg-surface-alt p-6">
                  <span className="font-mono text-eyebrow uppercase text-primary-hover">{card.kicker}</span>
                  <h3 className="mt-3 text-h3">{card.title}</h3>
                  <p className="mt-2 text-[14.5px]">{card.body}</p>
                  <div className="mt-auto pt-6">
                    {card.links.map((link) => (
                      <TextLink key={link.href + link.label} link={link} />
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="border-t border-line bg-surface-alt py-[clamp(64px,8vw,104px)]">
          <div className="mx-auto grid max-w-site items-center gap-10 px-4 sm:px-6 lg:grid-cols-[1fr_1fr]">
            <div data-reveal="">
              <Eyebrow>The numbers</Eyebrow>
              <h2 className="mt-3.5 text-[clamp(27px,3.1vw,38px)]">Four models, one gold set</h2>
              <p className="mt-4 max-w-[540px] text-lead">
                Gemini and Claude extract the same eight synthetic pulmonology notes; every fact must quote the source. A smoke test, not a
                benchmark, and the page says why.
              </p>
              {migration ? (
                <div className="mt-6 max-w-[540px] rounded-tile border border-line bg-white px-5 py-4">
                  <p className="font-mono text-[10.5px] uppercase tracking-[.1em] text-primary-hover">Your production model vs. the next one</p>
                  <p className="mt-2 text-[14px]">{migration.verdict}</p>
                  <div className="mt-3">
                    <TextLink link={{ href: "/evals#migration", label: "Opus 4.8 vs 5.5 in detail" }} />
                  </div>
                </div>
              ) : null}
            </div>
            <div data-reveal="">
              <EvalStats stats={stats} />
            </div>
          </div>
        </section>

        <section className="py-[clamp(56px,7vw,88px)]">
          <div data-reveal="" className="mx-auto flex max-w-site flex-wrap items-center gap-x-8 gap-y-4 px-4 sm:px-6">
            <h2 className="w-full text-[clamp(23px,2.6vw,30px)] md:w-auto md:flex-1">Read the code, the API and the numbers</h2>
            <TextLink link={{ href: GITHUB_URL, label: "Source on GitHub", external: true }} />
            {docs ? <TextLink link={{ href: docs, label: "API docs", external: true }} /> : null}
            <TextLink link={{ href: "/evals", label: "Eval report" }} />
          </div>
        </section>
      </Reveal>
    </>
  );
}
