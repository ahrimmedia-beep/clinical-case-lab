"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { PercentileCard } from "@/components/percentile/percentile-card";
import { Button, buttonClasses } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Eyebrow } from "@/components/ui/eyebrow";
import { ArrowIcon } from "@/components/ui/icons";
import type { AttemptResult } from "@/lib/api/types";
import { CalibrationCallout } from "./calibration-callout";
import { DebriefCard } from "./debrief-card";
import { FinalDiagnosis } from "./final-diagnosis";

type Props = { result: AttemptResult; revealedStages: ReadonlySet<string>; onPlayAgain: () => void };

export function DebriefView({ result, revealedStages, onPlayAgain }: Props) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    headingRef.current?.focus(); // keyboard and screen-reader users land on the result
  }, []);

  return (
    <section aria-labelledby="debrief-title" className="space-y-8">
      <header className="max-w-head">
        <Eyebrow>The debrief</Eyebrow>
        <h2 id="debrief-title" ref={headingRef} tabIndex={-1} className="mt-3 text-[clamp(27px,3.1vw,38px)] outline-none">
          See where the case turned
        </h2>
        <p className="mt-3 text-lead">
          Every decision you made, and the ones you went past. Points come only from the diagnosis and the treatment plan.
        </p>
      </header>
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <DebriefCard result={result} revealedStages={revealedStages} />
        <div className="space-y-6">
          <FinalDiagnosis final={result.final_diagnosis} diagnosis={result.diagnosis} />
          <PercentileCard result={result} />
          <CalibrationCallout diagnosis={result.diagnosis} />
          <Callout title="Nothing is attributable to you.">Your attempt is stored without a name, an account or an IP address.</Callout>
          <div className="flex flex-wrap items-center gap-3">
            <Link href="/cases" className={buttonClasses("primary")}>
              Next case <ArrowIcon />
            </Link>
            <Button variant="ghost" onClick={onPlayAgain}>
              Play again
            </Button>
            {/* C1 delta (amendments §E): sponsor-only aggregate view, gated server-side on the
                closed_<slug> cookie submitAttempt just set; the page itself is track C2's. */}
            <Link href={`/cases/${result.case_slug}/insights`} className={buttonClasses("link", "ml-auto")}>
              Sponsor view <ArrowIcon />
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
