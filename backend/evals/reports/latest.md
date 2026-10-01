# Extraction eval

Generated 2026-10-01T17:02:28+00:00 · prompt `v1` · 8 gold cases, no dev/test split

Read this first:

- The gold set is synthetic: 8 pulmonology case reports written for this repository; no real patient is described.
- Labels were drafted with an LLM before each text was written, then checked by hand and by automated consistency tests (every quote is found in the de-identified text; the labels score perfectly against themselves).
- 8 cases is a smoke-level harness: it catches regressions and large gaps between models; it is not a benchmark, and no confidence intervals are reported.
- Claude helped draft the labels and is also evaluated: a known bias in its favour.
- Findings count only on near-identical wording (token_sort_ratio >= 85, any word order), so a paraphrase that drops a qualifier is a miss; every model is scored the same way.
- Rows with provider `fake` are a harness self-check (damaged gold labels, no model call), not a model result.

| Model | Valid (1st try) | Macro-F1 | Findings F1 | Measurements F1 | Diagnosis | Grounded | Hallucinated | Negation errors | p50 / p95 ms | $ / case |
|---|---|---|---|---|---|---|---|---|---|---|
| fake/fake-gold | 100% (100%) | 0.991 | 0.945 | 1.000 | 100% | 98% | 1.9% | 0 | 40 / 40 | 0.0000 |

Macro-F1 averages six per-case scores (age, sex, chief complaint, diagnosis, findings F1, measurements F1), then averages over cases. Findings and measurements P/R/F1 are pooled over cases. Hallucinated = predicted items that match no gold item and whose evidence quote is not in the source. With eight cases, differences between models are indicative only.
