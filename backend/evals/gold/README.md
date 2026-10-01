# Gold set v1

Eight synthetic pulmonology case reports written for this repository, each with hand-checked
labels. No real patient is described. Names, dates, record numbers and phone numbers that appear
in some cases are invented on purpose, to exercise de-identification.

There is no dev/test split: eight cases are too few to hold any out, so every case is scored and
reported. Prompts are not tuned against individual gold cases. Eight cases make a smoke-level
harness that catches regressions and large differences between models; it is not a benchmark.

License: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — © 2026 ahrimmedia-beep.
You may reuse and adapt the cases with attribution.

## Cases

| id | Final diagnosis | Traps |
|---|---|---|
| `pe-01` | Pulmonary embolism | phi, negation, abbreviation, unit variant, distractor history |
| `lam-01` | Lymphangioleiomyomatosis | number in words, negation, abbreviation, unit variant, distractor history |
| `abpa-01` | Allergic bronchopulmonary aspergillosis | phi, negation, abbreviation, unit variant, distractor history |
| `aatd-01` | Alpha-1 antitrypsin deficiency | phi, negation, abbreviation, unit variant, number in words, distractor history |
| `pap-01` | Pulmonary alveolar proteinosis | number in words, negation, abbreviation, unit variant, distractor history |
| `sarc-01` | Sarcoidosis | negation, abbreviation, unit variant, distractor history |
| `ptx-01` | Primary spontaneous pneumothorax | phi, negation, abbreviation, unit variant, number in words, distractor history |
| `cap-01` | Community-acquired pneumonia | phi, negation, abbreviation, unit variant, number in words, distractor history |

## Files

- `manifest.yaml` — case ids and their final diagnoses.
- `<id>.txt` — the raw case report (the pipeline input).
- `<id>.json` — the labels: `ExtractedFacts` (the same model the pipeline returns) plus
  `diagnosis_aliases`, `measurement_aliases` (keyed by the gold measurement name), `negated`
  (phrases the text explicitly denies; predicting them as findings is a negation error) and
  `traps` (which hard cases the text contains).

## Labelling rules

1. Label only what the text states about this patient; the plan section is never labelled.
2. One finding per atomic statement; `text` is a short English paraphrase (at most 15 words,
   abbreviations expanded); `evidence` is an exact substring of the text, at least 8 characters,
   with no identifier inside it.
3. Measurements: one analyte per item; `value` as written in digits (numbers written in words
   converted), `unit` as written, `value_text` for non-numeric results (`128/76`, `positive`,
   `< 0.01`), `flag` only when the text marks the value.
4. Denied symptoms ("denies hemoptysis", "no clubbing") are never findings; they go to `negated`.
5. `tests/test_evals_gold.py` and `tests/test_evals_report.py` must pass: every quote is found in
   the de-identified text, every identifier is masked, and the labels scored against themselves
   give a perfect score.

## How the labels were made

Labels were drafted with an LLM before each text was written, then checked by hand against the
text and by the consistency tests above. Claude helped draft the labels and is also one of the
evaluated model families: that is a known bias of this set.
