# Extraction eval

Generated 2026-10-01T18:52:06+00:00 · prompt `v1` · 8 gold cases, no dev/test split

Read this first:

- The gold set is synthetic: 8 pulmonology case reports written for this repository; no real patient is described.
- Labels were drafted with an LLM before each text was written, then checked by hand and by automated consistency tests (every quote is found in the de-identified text; the labels score perfectly against themselves).
- 8 cases is a smoke-level harness: it catches regressions and large gaps between models; it is not a benchmark, and no confidence intervals are reported.
- Claude helped draft the labels and is also evaluated: a known bias in its favour.
- Findings count only on near-identical wording (token_sort_ratio >= 85, any word order), so a paraphrase that drops a qualifier is a miss; every model is scored the same way.
- The diagnosis rule was relaxed after the first live run: all four models were marked wrong on the same two cases while naming the right diagnosis more specifically (e.g. 'Sarcoidosis, Scadding stage II' for 'Sarcoidosis'). Naming the gold diagnosis as a phrase now counts; a hedge ('X or Y', 'X vs Y') still does not. All models were re-scored from the same answers.
- Route: Gemini runs on Vertex AI; Claude runs on the direct Anthropic API because Vertex AI granted this new project no Claude quota (NOT_ENOUGH_USAGE_HISTORY). Both go through the same provider interface with the same prompts, schema and scoring.

| Model | Valid (1st try) | Macro-F1 | Findings F1 | Measurements F1 | Diagnosis | Grounded | Hallucinated | Negation errors | p50 / p95 ms | $ / case |
|---|---|---|---|---|---|---|---|---|---|---|
| gemini/gemini-3.8-flash | 100% (100%) | 0.926 | 0.683 | 1.000 | 100% | 100% | 0.0% | 0 | 7934 / 17967 | 0.0071 |
| claude/claude-sonnet-5 | 100% (100%) | 0.952 | 0.744 | 0.975 | 100% | 100% | 0.0% | 7 | 10698 / 12970 | 0.0227 |
| claude/claude-opus-4-8 | 100% (100%) | 0.962 | 0.780 | 0.992 | 100% | 100% | 0.0% | 3 | 14056 / 16606 | 0.0550 |
| claude/claude-opus-5-5 | 100% (100%) | 0.970 | 0.820 | 1.000 | 100% | 100% | 0.0% | 2 | 12158 / 15406 | 0.0440 |

Macro-F1 averages six per-case scores (age, sex, chief complaint, diagnosis, findings F1, measurements F1), then averages over cases. Findings and measurements P/R/F1 are pooled over cases. Hallucinated = predicted items that match no gold item and whose evidence quote is not in the source. With eight cases, differences between models are indicative only.
