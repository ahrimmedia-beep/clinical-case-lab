import type { Metadata } from "next";
import { FieldChart } from "@/components/evals/field-chart";
import { ModelCallout } from "@/components/evals/model-callout";
import { ModelTable } from "@/components/evals/model-table";
import { Reveal } from "@/components/motion/reveal";
import { Callout } from "@/components/ui/callout";
import { Eyebrow } from "@/components/ui/eyebrow";
import { MonoTag } from "@/components/ui/mono-tag";
import { bestModel, compareModels, honestyNotes, isSelfCheck, loadEvalReport } from "@/lib/evals";
import { modelKey } from "@/lib/format";

export const metadata: Metadata = {
  title: "Evals",
  description: "Gemini and Claude on the same synthetic gold set: accuracy per field, hallucinations, latency and cost per case.",
};

const H2 = "text-[clamp(23px,2.6vw,30px)]";
const PRODUCTION_MODEL = "claude-opus-4-8";
const NEXT_MODEL = "claude-opus-5-5";

/** Renders `code` spans from the report's markdown-ish notes; everything else stays plain text. */
function NoteText({ text }: { text: string }) {
  return (
    <>
      {text.split("`").map((part, i) =>
        i % 2 === 1 ? (
          <code key={i} className="rounded-[4px] bg-surface-alt px-1 font-mono text-[12.5px] text-ink">
            {part}
          </code>
        ) : (
          part
        ),
      )}
    </>
  );
}

export default function EvalsPage() {
  const loaded = loadEvalReport();
  if (!loaded.ok) {
    return (
      <div className="mx-auto max-w-site px-4 py-16 sm:px-6">
        <div role="alert" className="max-w-[640px] rounded-card border border-line bg-surface-alt p-6">
          <h1 className="text-[22px]">The eval report doesn&apos;t match the expected shape</h1>
          <ul className="mt-3 list-disc pl-5 font-mono text-[12px] text-muted">
            {loaded.issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </div>
      </div>
    );
  }

  const { report } = loaded;
  const best = bestModel(report);
  const realModels = report.models.filter((m) => !isSelfCheck(m));
  const comparison = compareModels(report, PRODUCTION_MODEL, NEXT_MODEL);
  const notes = honestyNotes(report);
  const sample = report.sample === true;

  return (
    <Reveal className="mx-auto max-w-site px-4 py-[clamp(48px,7vw,96px)] sm:px-6">
      <header data-reveal="" className="max-w-head">
        <Eyebrow>Extraction evals</Eyebrow>
        <h1 className="mt-3 text-[clamp(27px,3.1vw,38px)]">Gemini and Claude on the same gold set</h1>
        <p className="mt-4 text-lead">
          {report.gold_cases} synthetic pulmonology case reports, the same prompt ({report.prompt_version}) for every model, and a verbatim source
          quote required for every extracted fact. It is a smoke test, not a benchmark:{" "}
          <a href="#limits" className="font-medium text-primary-hover underline decoration-primary-border underline-offset-4 hover:decoration-primary-hover">
            read its limits
          </a>
          .
        </p>
        <p className="mt-5 flex flex-wrap items-center gap-2">
          {sample ? <MonoTag tone="clay">Sample figures · replaced by the live run</MonoTag> : <MonoTag tone="teal">Live run</MonoTag>}
          <MonoTag>generated {report.generated_at.slice(0, 10)}</MonoTag>
          <MonoTag>{realModels.length} models</MonoTag>
          <MonoTag>labels LLM-drafted, hand-checked</MonoTag>
        </p>
        {sample ? (
          <p className="mt-3 text-[13.5px] text-muted">
            These numbers are placeholders with the right shape, committed before the live run on Vertex AI. The page reads the real report the
            moment it replaces this file.
          </p>
        ) : null}
        {report.models.some(isSelfCheck) ? (
          <p className="mt-3 text-[13.5px] text-muted">
            The grey row is a self-check: a deterministic fake provider that proves the harness scores correctly. It never ranks.
          </p>
        ) : null}
      </header>

      <section aria-labelledby="models-title" className="mt-14">
        <h2 id="models-title" data-reveal="" className={H2}>
          Model comparison
        </h2>
        <div className="mt-6">
          <ModelTable models={report.models} bestKey={best ? modelKey(best) : null} productionModel={PRODUCTION_MODEL} />
        </div>
      </section>

      <div data-reveal="" className="mt-14">
        <ModelCallout comparison={comparison} sample={sample} />
      </div>

      <section aria-labelledby="fields-title" className="mt-14">
        <h2 id="fields-title" data-reveal="" className={H2}>
          Accuracy by field
        </h2>
        <p data-reveal="" className="mt-3 max-w-[620px] text-[14.5px]">
          Where the models differ is in the long lists: findings and measurements. Demographics and the diagnosis are nearly solved; recall on
          findings is where a model leaves facts behind.
        </p>
        <div className="mt-6">
          <FieldChart models={report.models} />
        </div>
      </section>

      <section id="limits" aria-labelledby="limits-title" className="mt-14 grid gap-8 lg:grid-cols-[1.2fr_1fr]">
        <div data-reveal="">
          <h2 id="limits-title" className={H2}>
            Read this before the numbers
          </h2>
          <ul className="mt-5 space-y-3">
            {notes.map((note, i) => (
              <li key={note} className="flex gap-3 text-[14.5px]">
                <span aria-hidden="true" className="mt-0.5 font-mono text-[11px] text-muted">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span>
                  <NoteText text={note} />
                </span>
              </li>
            ))}
          </ul>
        </div>
        <Callout data-reveal="" className="self-start lg:mt-14" title="How to read this.">
          Macro-F1 averages six per-case scores (age, sex, chief complaint, diagnosis, findings F1, measurements F1). Quotes found means the
          model&apos;s verbatim quote was located in the source text. A hallucination is an extracted item that matches no labelled fact and whose
          quote is not in the source. Cost uses list prices per million tokens; thinking tokens count as output.
        </Callout>
      </section>
    </Reveal>
  );
}
