import { Callout } from "@/components/ui/callout";
import type { Calibration, DiagnosisResult } from "@/lib/api/types";

const COPY: Record<Calibration, (c: number) => { title: string; body: string }> = {
  overconfident: (c) => ({
    title: "Confidence ran ahead of the call.",
    body: `You rated ${c}/5 and the diagnosis didn't hold. Cases like this reward one more look at the workup.`,
  }),
  underconfident: (c) => ({
    title: "You were right, and less sure than you could have been.",
    body: `You rated ${c}/5 for a correct call. The findings supported more confidence.`,
  }),
  calibrated: (c) => ({
    title: "Your confidence matched the call.",
    body: `You rated ${c}/5, in line with how the case turned out.`,
  }),
};

export function CalibrationCallout({ diagnosis }: { diagnosis: DiagnosisResult }) {
  const { title, body } = COPY[diagnosis.calibration](diagnosis.confidence);
  return <Callout title={title}>{body}</Callout>;
}
