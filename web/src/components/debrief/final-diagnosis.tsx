import { Card, CardBody } from "@/components/ui/card";
import { Eyebrow } from "@/components/ui/eyebrow";
import { MonoTag } from "@/components/ui/mono-tag";
import { StateIcon, type Mark } from "@/components/ui/state-icon";
import type { AttemptResult } from "@/lib/api/types";

type Props = { final: AttemptResult["final_diagnosis"]; diagnosis: AttemptResult["diagnosis"] };

export function FinalDiagnosis({ final, diagnosis }: Props) {
  const mark: Mark = !diagnosis.answered ? "missed" : diagnosis.correct ? "right" : "wrong";
  return (
    <Card>
      <CardBody className="space-y-3 py-5">
        <Eyebrow>Final diagnosis</Eyebrow>
        <p className="flex flex-wrap items-center gap-2">
          <span className="text-[21px] font-semibold tracking-[-.02em] text-ink">{final.name}</span>
          {final.icd10 ? <MonoTag>ICD-10 {final.icd10}</MonoTag> : null}
        </p>
        <p className="flex items-start gap-2 text-[14px]">
          <StateIcon state={mark} />
          <span className="min-w-0 [overflow-wrap:anywhere]">
            <span className="text-muted">Your call, confidence {diagnosis.confidence}/5: </span>
            <span className="font-medium text-ink">{diagnosis.answered ? diagnosis.your_text : "no diagnosis given"}</span>
          </span>
        </p>
        {/* C1 delta (amendments §E): anti-hedging copy — naming several diagnoses scores as wrong. */}
        {diagnosis.hedged ? (
          <p className="flex items-start gap-2 rounded-row border border-missed-border bg-missed-tint px-3 py-2 text-[13px] text-ink">
            <StateIcon state="missed" label="Hedged" />
            You named several diagnoses — hedging earns no points.
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}
