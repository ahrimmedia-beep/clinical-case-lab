import Link from "next/link";
import { CaseFileCard } from "@/components/case/case-file-card";
import { buttonClasses } from "@/components/ui/button";
import { ArrowIcon } from "@/components/ui/icons";
import type { CaseSummary } from "@/lib/api/types";
import { formatInt } from "@/lib/format";

const HINTS = [
  { label: "Ask the questions that matter", hint: "the patient answers" },
  { label: "Open the differential", hint: "keep it wide" },
  { label: "Order the workup", hint: "where it turns" },
  { label: "Commit to a diagnosis and a plan", hint: "rate confidence" },
];

/** The hero case as an Eximion-style case file. Never names the diagnosis: the card links straight into the case. */
export function HeroCase({ hero, isRareDiseaseHero }: { hero: CaseSummary; isRareDiseaseHero: boolean }) {
  return (
    <div className="relative">
      {isRareDiseaseHero ? (
        <p className="mb-3 font-mono text-[11px] uppercase tracking-[.12em] text-primary-lit">The case most physicians miss</p>
      ) : null}
      <div className="rounded-[18px] shadow-on-dark">
        <CaseFileCard
          number={1}
          specialty={isRareDiseaseHero ? "rare disease" : hero.specialty}
          minutes={hero.estimated_minutes}
          title={hero.title}
          patient={hero.patient}
          difficulty={hero.difficulty}
          chiefComplaint={hero.chief_complaint}
          hints={HINTS}
          footer={
            <>
              <span>
                {hero.attempts_count > 0 ? `${formatInt(hero.attempts_count)} attempts so far` : "Be the first to close it"} · scored on the server
              </span>
              <Link href={`/cases/${hero.slug}`} className={buttonClasses("primary-sm", "ml-auto")}>
                Play the case <ArrowIcon />
              </Link>
            </>
          }
        />
      </div>
    </div>
  );
}
