import { ChevronIcon } from "@/components/ui/icons";
import { MonoTag } from "@/components/ui/mono-tag";
import { StateIcon } from "@/components/ui/state-icon";
import { DECISION_LABEL } from "@/lib/facts";

/** One decision stage as an author or reviewer sees it: the key is visible on purpose. */
export type KeyStage = {
  stage: string;
  prompt: string;
  explanation: string;
  options: { key: string; text: string; is_correct: boolean; is_harmful: boolean; feedback?: string | null; reveal?: string | null }[];
  /** Diagnosis stage only. */
  accepted?: string[];
};

type Props = { stages: KeyStage[]; finalDiagnosis: string; open?: "first" | "all" };

function count(stage: KeyStage): string {
  if (stage.options.length === 0) return `${stage.accepted?.length ?? 0} accepted`;
  const correct = stage.options.filter((o) => o.is_correct).length;
  const harmful = stage.options.filter((o) => o.is_harmful).length;
  return `${correct} of ${stage.options.length} correct${harmful > 0 ? ` · ${harmful} harmful` : ""}`;
}

/** Answer key per decision stage; options carry a ✓ when correct and a clay tag when harmful. Works in server and client trees. */
export function AnswerKeyList({ stages, finalDiagnosis, open = "first" }: Props) {
  return (
    <div className="divide-y divide-line">
      {stages.map((d, i) => (
        <details key={d.stage} open={open === "all" || i === 0} className="group px-5 py-3.5">
          <summary className="flex cursor-pointer list-none items-center gap-3 [&::-webkit-details-marker]:hidden">
            <span className="font-mono text-[10.5px] uppercase tracking-[.1em] text-primary-hover">{DECISION_LABEL[d.stage] ?? d.stage}</span>
            <span className="ml-auto font-mono text-[10.5px] text-muted">{count(d)}</span>
            <ChevronIcon className="text-muted transition-transform group-open:rotate-90" />
          </summary>
          <p className="mt-2.5 text-[14.5px] font-medium text-ink">{d.prompt}</p>
          {d.options.length > 0 ? (
            <ul className="mt-2.5 space-y-2">
              {d.options.map((o) => (
                <li key={o.key} className="flex items-start gap-2.5 text-[13.5px] [overflow-wrap:anywhere]">
                  <StateIcon state={o.is_correct ? "right" : "neutral"} label={o.is_correct ? "Correct option" : "Not a correct option"} className="mt-0.5" />
                  <span className="min-w-0 flex-1">
                    <span className="mr-1.5 font-mono text-[11px] text-muted">{o.key}</span>
                    <span className="text-ink">{o.text}</span>
                    {o.is_harmful ? (
                      <MonoTag tone="clay" className="ml-2 align-middle">
                        harmful
                      </MonoTag>
                    ) : null}
                    {o.reveal ? <span className="mt-0.5 block text-[12.5px] text-muted">Reveal: {o.reveal}</span> : null}
                    {o.feedback ? <span className="mt-0.5 block text-[12.5px] text-body">Feedback: {o.feedback}</span> : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-2.5 flex items-start gap-2.5 text-[13.5px]">
              <StateIcon state="right" label="Correct answer" className="mt-0.5" />
              <p className="min-w-0 flex-1 [overflow-wrap:anywhere]">
                <span className="font-medium text-ink">{finalDiagnosis}</span>
                {d.accepted && d.accepted.filter((a) => a !== finalDiagnosis).length > 0 ? (
                  <span className="block text-[12.5px] text-muted">Also accepted: {d.accepted.filter((a) => a !== finalDiagnosis).join(", ")}</span>
                ) : null}
              </p>
            </div>
          )}
          <p className="mt-3 rounded-[8px] bg-surface-alt px-3 py-2 text-[12.5px] text-body">
            <span className="font-mono text-[10px] uppercase tracking-[.1em] text-muted">Debrief · </span>
            {d.explanation}
          </p>
        </details>
      ))}
    </div>
  );
}
