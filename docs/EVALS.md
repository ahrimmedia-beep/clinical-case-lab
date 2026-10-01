# Eval harness

A small, honest extraction-accuracy harness for `backend/pipeline`: how well each model turns a
raw clinical case report into the structured `ExtractedFacts` the rest of the pipeline builds on.
It is not a benchmark of medical reasoning — the player, the scoring and the debrief need no
model at all. This measures only the one LLM step that reads free text.

## What it measures, and why

| Metric | What it is | Why it is here |
|---|---|---|
| `schema_valid_rate` / `schema_valid_first_try_rate` | fraction of calls that parsed into `ExtractedFacts`, with and without the repair round | a model that cannot hold the schema is unusable regardless of accuracy |
| `patient_age`, `patient_sex` | exact match against gold | cheap, unambiguous correctness checks |
| `chief_complaint` | fuzzy match (`token_sort_ratio`) | free text rarely matches gold verbatim; this rewards the right content, not the right wording |
| `final_diagnosis` | alias list + fuzzy match | the one fact every downstream stage depends on |
| `findings_precision/recall/f1` | greedy fuzzy matching of extracted findings against gold, `token_sort_ratio ≥ 85` | pooled across all 8 cases, so one bad case cannot be hidden by seven good ones; the 85 threshold is deliberately strict — `token_set_ratio` would score "cough" against "cough with blood-streaked sputum" as a perfect match, which is a miss, not a hit |
| `measurements_precision/recall/f1` | name/alias match + value within 2% + unit match | numbers are either right or wrong; a near-miss value is still wrong |
| `negation_errors` | count of findings whose polarity (present/absent) the model flipped | a flipped negation ("no fever" → "fever") is more dangerous than a missed finding |
| `grounded_ratio` | fraction of extracted items whose evidence quote is found verbatim in the de-identified source | this is the project's core LLM-reliability claim: every fact must point at the text that supports it |
| `hallucination_rate` | predicted items that match no gold item **and** have no grounded quote | an invented-and-unsupported fact, the worst failure mode |
| `latency_ms_p50` / `p95`, `tokens_in/out_avg`, `cost_usd_per_case` | operational numbers from the live calls | the harness also answers "which model is cheap and fast enough to run on every case" |
| `macro_f1` | mean of six per-case scores (age, sex, chief complaint, diagnosis, findings F1, measurements F1), averaged over cases | one headline number per model for the table and the `/evals` page |

## The gold set

8 synthetic pulmonology case reports, written for this repository — no real patient data:
pulmonary embolism (PE), lymphangioleiomyomatosis (LAM, the hero case), allergic
bronchopulmonary aspergillosis (ABPA), alpha-1 antitrypsin deficiency (AATD), pulmonary alveolar
proteinosis (PAP), sarcoidosis, spontaneous pneumothorax, and community-acquired pneumonia (CAP).
No dev/test split — all 8 are scored every run (`split: "all"` in the report, kept for the web
contract).

Each case carries deliberate traps so a model that merely pattern-matches on surface cues scores
worse than one that reads carefully: negations ("no fever" / "denies"), abbreviations (ABPA,
AATD, A1AT), unit variants (mg/L vs mg/dL, mmHg vs kPa), distractor history, and at least one
measurement written out in words instead of digits.

Gold labels are `ExtractedFacts` plus an alias list per case (diagnosis names and measurement
names), so a model that says "PE" is not marked wrong against gold "pulmonary embolism".

## How to run it

```bash
make eval-offline      # CI-safe: re-scores the recordings committed under backend/evals/recordings/
                        # — no API keys, no network, used by the metric floor test.
make eval              # live: calls all four models in pipeline/pricing.yaml on all 8 cases.
                        # Needs GCP_PROJECT + Application Default Credentials
                        # (gcloud auth application-default login) and a network region Google
                        # serves (or run it from Cloud Shell instead). Vertex AI model calls
                        # never go from a network Google does not serve.
make sync-evals        # copies backend/evals/reports/latest.json into web/src/data/, which the
                        # /evals page renders.
```

Equivalent direct calls: `python -m evals.run --offline` and `python -m evals.run --models
gemini/gemini-3.8-flash,claude/claude-sonnet-5` (narrow to any subset with `--models`).

**Resumable by design.** Every finished model call is appended to
`backend/evals/.cache/<provider>__<model>__<prompt_version>.jsonl` immediately (flushed and
fsynced), so a crash or Ctrl-C loses at most the one case in flight. Re-running `make eval` skips
every case already in the cache — a full rerun after an interruption only pays for what is
missing. 429/5xx errors back off from 10 s to 120 s for up to ~30 minutes before the run gives up
on that model; finished cases from other models are untouched. A finished model's cache file is
copied into `backend/evals/recordings/` (committed) so CI can re-score it without network access.

After a live run, `python3 scripts/update_eval_tables.py` copies the first Markdown table of
`backend/evals/reports/latest.md` into this file and into `README.md`, between the
eval-table markers below (an HTML comment pair; see "The current table").

## How CI uses this

CI never calls a model. `make eval-offline` re-scores the committed `backend/evals/recordings/`
files, and `backend/tests/test_evals_floor.py` asserts each recording's `macro_f1` stays at or
above a floor: 0.90 for the `fake/fake-gold` self-check row (a harness sanity check — damaged gold
labels with a deterministic fake provider, not a model result), 0.60 for every live-model
recording once one exists. The floor exists to catch a regression in the pipeline or the metrics,
not to grade models against each other; it is set well below any real model's observed score so
normal variance never fails a build.

## Honesty notes

- The gold set is synthetic: 8 pulmonology case reports written for this repository; no real
  patient is described.
- Labels were drafted with an LLM before each case report was written, then checked by hand and
  by automated consistency tests (every evidence quote is found in the de-identified text; the
  labels score perfectly against themselves).
- 8 cases is a smoke-level harness: it catches regressions and large gaps between models; it is
  not a benchmark, and no confidence intervals are reported.
- Claude helped draft the labels and is also evaluated: a known bias in its favour.
- Findings count only on near-identical wording (`token_sort_ratio ≥ 85`, any word order), so a
  paraphrase that drops a qualifier is a miss; every model is scored the same way.

## Opus 4.8 vs Opus 5.5

Two Claude models are evaluated side by side on purpose: `claude-opus-4-8` is what Eximion's own
AI disclosure names as their production model, and `claude-opus-5-5` is Anthropic's newer,
cheaper successor (see `backend/pipeline/pricing.yaml`: $5/$25 per 1M input/output tokens for
Opus 4.8 vs $4/$20 for Opus 5.5). The `/evals` page reads this table to compare the two on
accuracy, latency and cost per case, as a concrete, reproducible answer to "should production
move to the newer model" rather than a guess.

## The current table

A live run of the four models in `pipeline/pricing.yaml` on all 8 gold cases, following the steps
above. A separate `fake/fake-gold` row (a deterministic fake provider against deliberately damaged
gold labels) is not shown here; it exists only as a harness sanity check and backs the metric
floor test in CI (see "How CI uses this").

<!-- The table between the markers is generated: python3 scripts/update_eval_tables.py copies the first table of backend/evals/reports/latest.md. -->
<!-- eval-table:start -->
| Model | Valid (1st try) | Macro-F1 | Findings F1 | Measurements F1 | Diagnosis | Grounded | Hallucinated | Negation errors | p50 / p95 ms | $ / case |
|---|---|---|---|---|---|---|---|---|---|---|
| gemini/gemini-3.8-flash | 100% (100%) | 0.926 | 0.683 | 1.000 | 100% | 100% | 0.0% | 0 | 7934 / 17967 | 0.0071 |
| claude/claude-sonnet-5 | 100% (100%) | 0.952 | 0.744 | 0.975 | 100% | 100% | 0.0% | 7 | 10698 / 12970 | 0.0227 |
| claude/claude-opus-4-8 | 100% (100%) | 0.962 | 0.780 | 0.992 | 100% | 100% | 0.0% | 3 | 14056 / 16606 | 0.0550 |
| claude/claude-opus-5-5 | 100% (100%) | 0.970 | 0.820 | 1.000 | 100% | 100% | 0.0% | 2 | 12158 / 15406 | 0.0440 |
<!-- eval-table:end -->

## Cloud Run Job variant (not used)

The original plan ran the live eval as a Cloud Run Job (`evals`, on the `api` image, with Cloud
Storage volumes for `reports/` and `.cache/`, driven by a script that would copy the job's
reports back into the repo) so the caller's machine never had to reach Vertex AI directly. For this submission that path is **WON'T**: the live eval
instead runs directly from the developer's machine on a network region Google serves (or from
Cloud Shell), using `make eval` as documented above — simpler to operate for a one-time run, at
the cost of needing that one command to run somewhere Google serves. `infra/deploy.sh` keeps `ENABLE_EVALS=0`
by default and never deploys the `evals` job or its bucket; setting `ENABLE_EVALS=1` restores the
job definition (`python -m evals.run`, mounted on `gs://<project>-case-lab-evals/{reports,cache}`)
for anyone who wants the Cloud Run Job path later.
