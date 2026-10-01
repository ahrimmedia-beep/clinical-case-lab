import { MonoTag } from "@/components/ui/mono-tag";
import type { CasePublic, PublicStage, StageItem } from "@/lib/api/types";
import { formatPatient } from "@/lib/format";

const CATEGORY: Record<string, string> = {
  symptom: "Symptom", history: "History", medication: "Medication", allergy: "Allergy", social: "Social",
  family: "Family", exam: "Exam", imaging: "Imaging", procedure: "Procedure", vital: "Vital", lab: "Lab",
};
// Lab flags stay neutral: teal, clay and amber are reserved for the debrief's right / wrong / missed.
const FLAG: Record<string, string> = { high: "↑ high", low: "↓ low", abnormal: "abnormal" };

type Props = { stage: PublicStage; caseData: Pick<CasePublic, "patient" | "chief_complaint" | "vignette"> };

/** A "given to you" stage. Rendered on the server and passed to the client player as a prop. */
export function GivenStage({ stage, caseData }: Props) {
  const opening = stage.key === "presenting_complaint";
  const items = stage.items ?? [];
  const measurements = items.filter((item) => item.kind === "measurement");
  const findings = items.filter((item) => item.kind === "finding");
  return (
    <div className="space-y-5">
      {opening ? (
        <div className="space-y-3">
          <p className="text-[12.5px] text-muted">
            {caseData.patient.display_name ? `${caseData.patient.display_name} · ` : ""}
            {formatPatient(caseData.patient)}
          </p>
          <p className="text-h3 text-ink [overflow-wrap:anywhere]">{caseData.chief_complaint}</p>
          <p className="max-w-[620px] text-[15px] leading-[1.7] text-body">{caseData.vignette}</p>
        </div>
      ) : null}
      {measurements.length > 0 ? <MeasurementTable items={measurements} /> : null}
      {findings.length > 0 ? <FindingList items={findings} /> : null}
      {!opening && items.length === 0 ? <p className="text-[14px] text-muted">Nothing recorded at this stage.</p> : null}
    </div>
  );
}

function Withheld() {
  return (
    <span className="inline-flex flex-wrap items-center gap-2 font-normal italic text-muted">
      Result withheld until the debrief
      <MonoTag>withheld</MonoTag>
    </span>
  );
}

function MeasurementTable({ items }: { items: StageItem[] }) {
  return (
    <table className="w-full text-[14px]">
      <caption className="sr-only">Measurements</caption>
      <thead className="sr-only">
        <tr>
          <th scope="col">Measurement</th>
          <th scope="col">Value</th>
          <th scope="col">Flag</th>
        </tr>
      </thead>
      <tbody>
        {items.map((m, i) => (
          <tr key={`${m.text}-${i}`} className="border-t border-line first:border-0">
            <th scope="row" className="py-2 pr-3 text-left font-normal text-body">
              <span className="mr-2 font-mono text-[10px] uppercase tracking-[.08em] text-muted">{CATEGORY[m.category] ?? m.category}</span>
              {m.text}
            </th>
            <td className="py-2 text-end font-medium tabular-nums text-ink">
              {m.withheld ? (
                <Withheld />
              ) : (
                <>
                  {m.value ?? "—"}
                  {m.unit ? <span className="ml-1 text-[12px] font-normal text-muted">{m.unit}</span> : null}
                </>
              )}
            </td>
            <td className="w-[86px] py-2 pl-3 text-end">{m.flag && FLAG[m.flag] ? <MonoTag>{FLAG[m.flag]}</MonoTag> : null}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function FindingList({ items }: { items: StageItem[] }) {
  return (
    <ul>
      {items.map((f, i) => (
        <li key={`${f.text}-${i}`} className="flex gap-3 border-t border-line py-2.5 first:border-0">
          <span className="w-[84px] flex-none pt-0.5 font-mono text-[10px] uppercase tracking-[.08em] text-muted">{CATEGORY[f.category] ?? f.category}</span>
          <span className="min-w-0 text-[14.5px] text-ink [overflow-wrap:anywhere]">{f.withheld ? <Withheld /> : f.text}</span>
        </li>
      ))}
    </ul>
  );
}
