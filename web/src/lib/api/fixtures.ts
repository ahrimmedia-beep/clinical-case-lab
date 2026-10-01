import "server-only";
import type {
  AttemptIn,
  AttemptResult,
  Benchmark,
  CaseCreated,
  CasePublic,
  CaseSummary,
  ClinicalCase,
  DebriefOption,
  DebriefStage,
  EvidenceSpan,
  ExtractResponse,
  OptionState,
  PublicOption,
  PublicStage,
  RevealIn,
  RevealOut,
  Stage,
  StageItem,
} from "./types";

/*
 * Fixture mode (API_BASE_URL unset) and unit tests use these. The PE case mirrors
 * backend/tests/fixtures/case_pe.json as GET /api/cases/{slug} serves it. Server-only because
 * the debrief and the extraction carry answers. Fixture mode does not score: every attempt
 * gets the same canned debrief with the player's own diagnosis text echoed back.
 */

const finding = (category: string, text: string): StageItem => ({
  kind: "finding", category, text, value: null, unit: null, flag: null, withheld: false,
});

const measurement = (category: "vital" | "lab", text: string, value: string, unit: string, flag: StageItem["flag"]): StageItem => ({
  kind: "measurement", category, text, value, unit, flag, withheld: false,
});

function given(number: number, key: Stage, label: string, items: StageItem[]): PublicStage {
  return { number, key, label, hint: "given to you", kind: "given", scored: false, items, prompt: null, input: null, options: [] };
}

function decision(
  number: number, key: Stage, label: string, hint: string, prompt: string,
  input: "multi_select" | "free_text", options: PublicOption[], scored = false,
): PublicStage {
  return { number, key, label, hint, kind: "decision", scored, items: [], prompt, input, options };
}

const HISTORY_ITEMS = [
  finding("symptom", "Pleuritic right-sided chest pain"),
  finding("history", "14-hour flight the day before"),
  finding("medication", "Combined oral contraceptive pill"),
];
const EXAM_ITEMS = [
  measurement("vital", "Heart rate", "112", "bpm", "high"),
  measurement("vital", "SpO2", "91", "%", "low"),
  finding("exam", "Swollen, tender left calf"),
];
const RESULTS_ITEMS = [
  measurement("lab", "D-dimer", "2.4", "mg/L FEU", "high"),
  finding("imaging", "CT pulmonary angiography: filling defect in the right lower lobe pulmonary artery"),
];

const INTERVIEW_OPTIONS: PublicOption[] = [
  { key: "A", text: "Any recent long travel or immobility?" },
  { key: "B", text: "Does she take any hormonal medication?" },
  { key: "C", text: "Did she have asthma as a child?" },
];
const DIFFERENTIAL_OPTIONS: PublicOption[] = [
  { key: "A", text: "Pulmonary embolism" },
  { key: "B", text: "Pneumothorax" },
  { key: "C", text: "Gastro-oesophageal reflux" },
];
const WORKUP_OPTIONS: PublicOption[] = [
  { key: "A", text: "CT pulmonary angiography" },
  { key: "B", text: "D-dimer" },
  { key: "C", text: "Spirometry" },
];
const TREATMENT_OPTIONS: PublicOption[] = [
  { key: "A", text: "Start anticoagulation (apixaban or LMWH)" },
  { key: "B", text: "Stop the combined oral contraceptive" },
  { key: "C", text: "Systemic thrombolysis" },
];

export const peCasePublic: CasePublic = {
  id: 1,
  slug: "sudden-breathlessness-after-a-long-flight-3f9a1c",
  title: "Sudden breathlessness after a long flight",
  specialty: "pulmonology",
  difficulty: "easy",
  estimated_minutes: 5,
  patient: { display_name: "Ms. R.", age_years: 34, sex: "female" },
  chief_complaint: "Sudden shortness of breath and right-sided chest pain",
  vignette:
    "A 34-year-old woman comes to the emergency department with sudden shortness of breath and sharp right-sided chest pain that worsens on inspiration. She returned yesterday from a 14-hour flight.",
  source_kind: "manual",
  review_status: "approved", // C1 delta (amendments §E): physician-reviewed catalogue shelf
  stages: [
    given(1, "presenting_complaint", "Presenting complaint", []),
    given(2, "history", "History", HISTORY_ITEMS),
    decision(3, "interview", "Patient interview", "questions you asked", "What do you ask her first?", "multi_select", INTERVIEW_OPTIONS),
    given(4, "examination", "Examination", EXAM_ITEMS),
    decision(5, "differential", "Differential", "entries you listed", "Which diagnoses do you keep open?", "multi_select", DIFFERENTIAL_OPTIONS),
    decision(6, "workup", "Workup", "tests you ordered", "Which tests do you order first?", "multi_select", WORKUP_OPTIONS),
    given(7, "results", "Results", RESULTS_ITEMS),
    decision(8, "diagnosis", "Diagnosis", "the call you made", "What is your diagnosis?", "free_text", [], true),
    decision(9, "treatment", "Treatment plan", "the plan you built", "What is your initial plan?", "multi_select", TREATMENT_OPTIONS, true),
  ],
};

const LONG =
  " — with a deliberately long clause that keeps going so the chip has to wrap across several lines on a 390 px screen, plus one unbroken token: Methylprednisolonesodiumsuccinate1000mgIVoverthreedays";

/** Review Focus #3/#4: no interview or workup, an empty given stage, a withheld result, very long option texts. */
export const stressCasePublic: CasePublic = {
  ...peCasePublic,
  id: 99,
  slug: "layout-stress-test",
  title: "Layout stress test: long options, missing stages, a withheld result",
  stages: peCasePublic.stages
    .filter((s) => s.key !== "interview" && s.key !== "workup")
    .map((s): PublicStage => {
      if (s.key === "examination") return { ...s, items: [] };
      if (s.key === "results") {
        return { ...s, items: [...(s.items ?? []), { ...finding("imaging", "Result withheld until the debrief"), withheld: true }] };
      }
      return { ...s, options: (s.options ?? []).map((o) => ({ ...o, text: o.text + LONG })) };
    }),
};

/**
 * C1 delta (amendments §E): a second catalogue shelf — "AI drafts, awaiting physician review" —
 * needs at least one draft-status, LLM-sourced case to render in fixture mode. Same stages as
 * the PE case (this is a UI fixture, not new clinical content); only the status/source differ.
 */
export const draftCasePublic: CasePublic = {
  ...peCasePublic,
  id: 2,
  slug: "recurrent-pneumothorax-after-exertion-ai-draft",
  title: "Recurrent pneumothorax after exertion",
  source_kind: "llm",
  review_status: "draft",
};

const ALL_CASES = [peCasePublic, draftCasePublic, stressCasePublic];

function summary(c: CasePublic, attempts: number): CaseSummary {
  return {
    id: c.id,
    slug: c.slug,
    title: c.title,
    specialty: c.specialty,
    difficulty: c.difficulty,
    estimated_minutes: c.estimated_minutes,
    patient: c.patient,
    chief_complaint: c.chief_complaint,
    decision_count: c.stages.filter((s) => s.kind === "decision").length,
    attempts_count: attempts,
    source_kind: c.source_kind,
    review_status: c.review_status, // C1 delta: drives the catalogue's approved / draft shelves
    created_at: "2026-10-01T09:00:00Z",
  };
}

export const caseSummaries: CaseSummary[] = [summary(peCasePublic, 212), summary(draftCasePublic, 0), summary(stressCasePublic, 0)];

export function findCase(slug: string): CasePublic | null {
  return ALL_CASES.find((c) => c.slug === slug) ?? null;
}

const PE_REVEALS: Record<RevealIn["stage"], Record<string, string>> = {
  interview: { A: "Yes, a 14-hour flight yesterday.", B: "A combined oral contraceptive pill.", C: "No." },
  workup: { A: "Filling defect in the right lower lobe pulmonary artery.", B: "2.4 mg/L FEU (raised).", C: "Not performed." },
};

export function revealsFor(_slug: string, body: RevealIn): RevealOut[] {
  const table = PE_REVEALS[body.stage];
  return body.option_keys.flatMap((key) => (table[key] ? [{ key, reveal: table[key] }] : []));
}

function stageOf(key: Stage): PublicStage {
  const stage = peCasePublic.stages.find((s) => s.key === key);
  if (!stage) throw new Error(`fixture stage ${key} missing`);
  return stage;
}

function opt(
  key: string, text: string, chosen: boolean, state: OptionState, pickRate: number,
  extra: Partial<Pick<DebriefOption, "is_harmful" | "feedback" | "reveal">> = {},
): DebriefOption {
  return { key, text, chosen, state, is_harmful: false, feedback: null, reveal: null, pick_rate: pickRate, ...extra };
}

function debriefStage(stage: PublicStage, options: DebriefOption[] = [], explanation: string | null = null, points = 0, maxPoints = 0): DebriefStage {
  const count = (state: OptionState) => options.filter((o) => o.state === state).length;
  return {
    number: stage.number, key: stage.key, label: stage.label, hint: stage.hint, kind: stage.kind, scored: stage.scored,
    right: count("right"), wrong: count("wrong"), missed: count("missed"), points, max_points: maxPoints,
    explanation, options, items: stage.items,
  };
}

/**
 * C1 delta (amendments §E): the percentile card draws these as labelled markers next to the
 * player's own result, e.g. "Claude Opus 4.8 · 2/3 · overconfident". Three of the four §15
 * models; the fourth (claude-opus-5-5) is left out of this canned attempt on purpose, the same
 * way a real cohort would not have every model benchmarked on every case yet.
 *
 * `label` mirrors the real API: it is the raw `simulated_label` tag (`ai:{model}`, amendments
 * §C Track A Task 6), not display text — the UI must format it with `modelLabel(b.model)`
 * instead of rendering `label` directly (found against the live API by track C2).
 */
const PE_BENCHMARKS: Benchmark[] = [
  { label: "ai:claude-opus-4-8", provider: "claude", model: "claude-opus-4-8", points: 2, max_points: 3, diagnosis_correct: true, confidence: 5, calibration: "overconfident" },
  { label: "ai:claude-sonnet-5", provider: "claude", model: "claude-sonnet-5", points: 1, max_points: 3, diagnosis_correct: true, confidence: 3, calibration: "calibrated" },
  { label: "ai:gemini-3.8-flash", provider: "gemini", model: "gemini-3.8-flash", points: 0, max_points: 3, diagnosis_correct: false, confidence: 4, calibration: "overconfident" },
];

/** C1 delta (amendments §E): the anti-hedging rule from §9, loosely mirrored for the fixture echo only. */
function looksHedged(text: string): boolean {
  return /(,|\/|;| or | and\/or | vs\.?|versus)/i.test(text.trim());
}

/** Canned attempt: interview A+C, differential A+B, workup A+B+C, diagnosis right (4/5), treatment A. */
export const peAttemptResult: AttemptResult = {
  attempt_id: 4211,
  case_slug: peCasePublic.slug,
  points: 2,
  max_points: 3,
  right: 7,
  wrong: 2,
  missed: 2,
  harmful: 0,
  total_decisions: 9, // backend: correct options across multi-select stages (2+2+2+2) + 1 for the diagnosis
  percentile: 64.5,
  cohort_size: 212,
  cohort_is_simulated: true,
  benchmarks: PE_BENCHMARKS,
  histogram: [
    { points: 0, count: 18 },
    { points: 1, count: 47 },
    { points: 2, count: 96 },
    { points: 3, count: 51 },
  ],
  final_diagnosis: { name: "Pulmonary embolism", icd10: "I26.99", evidence: null },
  diagnosis: { your_text: "Pulmonary embolism", correct: true, answered: true, confidence: 4, calibration: "calibrated", hedged: false },
  stages: [
    debriefStage(stageOf("presenting_complaint")),
    debriefStage(stageOf("history")),
    debriefStage(
      stageOf("interview"),
      [
        opt("A", "Any recent long travel or immobility?", true, "right", 0.81, { reveal: "Yes, a 14-hour flight yesterday." }),
        opt("B", "Does she take any hormonal medication?", false, "missed", 0.64, { reveal: "A combined oral contraceptive pill." }),
        opt("C", "Did she have asthma as a child?", true, "wrong", 0.22, { feedback: "Low yield for an acute presentation like this one.", reveal: "No." }),
      ],
      "Recent long-haul travel and oestrogen exposure are the key venous thromboembolism risk factors here.",
    ),
    debriefStage(stageOf("examination")),
    debriefStage(
      stageOf("differential"),
      [
        opt("A", "Pulmonary embolism", true, "right", 0.93),
        opt("B", "Pneumothorax", true, "right", 0.71),
        opt("C", "Gastro-oesophageal reflux", false, "neutral", 0.12, { feedback: "Does not explain hypoxia or tachycardia." }),
      ],
      "Sudden pleuritic pain with hypoxia needs pulmonary embolism and pneumothorax ruled in or out first.",
    ),
    debriefStage(
      stageOf("workup"),
      [
        opt("A", "CT pulmonary angiography", true, "right", 0.88, { reveal: "Filling defect in the right lower lobe pulmonary artery." }),
        opt("B", "D-dimer", true, "right", 0.74, { reveal: "2.4 mg/L FEU (raised)." }),
        opt("C", "Spirometry", true, "wrong", 0.09, { feedback: "Not useful in the acute setting.", reveal: "Not performed." }),
      ],
      "With a high clinical probability, go straight to CT pulmonary angiography; D-dimer supports but cannot exclude.",
    ),
    debriefStage(stageOf("results")),
    {
      ...debriefStage(stageOf("diagnosis"), [], "Risk factors, a swollen calf, hypoxia and a CTPA filling defect confirm an acute pulmonary embolism.", 1, 1),
      right: 1,
    },
    debriefStage(
      stageOf("treatment"),
      [
        opt("A", "Start anticoagulation (apixaban or LMWH)", true, "right", 0.95),
        opt("B", "Stop the combined oral contraceptive", false, "missed", 0.58),
        opt("C", "Systemic thrombolysis", false, "neutral", 0.07, {
          is_harmful: true,
          feedback: "Thrombolysis is reserved for high-risk (massive) PE; in a stable patient the bleeding risk outweighs the benefit.",
        }),
      ],
      "Haemodynamically stable PE: anticoagulate and remove the provoking factor.",
      1,
      2,
    ),
  ],
};

export function attemptResultFor(slug: string, body: AttemptIn): AttemptResult {
  // One line per recorded attempt: lets the double-click check count submissions in the dev log.
  console.info(`[fixture] attempt recorded for ${slug}`);
  return {
    ...peAttemptResult,
    case_slug: slug,
    diagnosis: {
      ...peAttemptResult.diagnosis,
      your_text: body.diagnosis_text,
      answered: body.diagnosis_text.trim().length > 0,
      confidence: body.confidence,
      hedged: looksHedged(body.diagnosis_text),
    },
  };
}

const EXTRACT_SOURCE =
  "ED note, [DATE_1]. [NAME_1] is a 34-year-old woman with sudden shortness of breath and sharp right-sided chest pain that worsens on inspiration. She returned yesterday from a 14-hour flight. She takes a combined oral contraceptive. She denies fever or cough. On examination: heart rate 112, blood pressure 124/78, SpO2 91% on room air. The left calf is swollen and tender. Labs: D-dimer 2.4 mg/L FEU. CT pulmonary angiography shows a filling defect in the right lower lobe pulmonary artery. Impression: acute pulmonary embolism. Callback number [PHONE_1].";

const EXTRACTED_CASE: ClinicalCase = {
  schema_version: "1.0",
  title: "Sudden breathlessness after a long flight",
  specialty: "pulmonology",
  difficulty: "easy",
  estimated_minutes: 5,
  patient: { display_name: null, age_years: 34, sex: "female" },
  chief_complaint: "Sudden shortness of breath and right-sided chest pain",
  vignette:
    "A 34-year-old woman comes to the emergency department with sudden shortness of breath and sharp right-sided chest pain that worsens on inspiration. She returned yesterday from a 14-hour flight.",
  findings: [
    { category: "symptom", text: "Pleuritic right-sided chest pain", evidence: "sharp right-sided chest pain that worsens on inspiration" },
    { category: "history", text: "14-hour flight the day before", evidence: "returned yesterday from a 14-hour flight" },
    { category: "medication", text: "Combined oral contraceptive pill", evidence: "takes a combined oral contraceptive" },
    { category: "exam", text: "Swollen, tender left calf", evidence: "left calf is swollen and tender" },
    { category: "imaging", text: "CT pulmonary angiography: filling defect in the right lower lobe pulmonary artery", evidence: "filling defect in the right lower lobe pulmonary artery" },
    // Deliberately ungrounded: the model "remembered" a sign the note never mentions.
    { category: "exam", text: "Pleural rub over the right base", evidence: "pleural rub heard at the right base" },
  ],
  measurements: [
    { kind: "vital", name: "Heart rate", value: 112, value_text: null, unit: "bpm", flag: "high", evidence: "heart rate 112" },
    { kind: "vital", name: "SpO2", value: 91, value_text: null, unit: "%", flag: "low", evidence: "SpO2 91% on room air" },
    { kind: "lab", name: "D-dimer", value: 2.4, value_text: null, unit: "mg/L FEU", flag: "high", evidence: "D-dimer 2.4 mg/L FEU" },
  ],
  final_diagnosis: { name: "Pulmonary embolism", icd10: "I26.99", evidence: "acute pulmonary embolism" },
  differential: [{ name: "Pneumothorax", icd10: "J93.9", evidence: null }],
  decisions: [
    {
      stage: "interview",
      prompt: "What do you ask her first?",
      explanation: "Recent long-haul travel and oestrogen exposure are the key venous thromboembolism risk factors here.",
      options: [
        { key: "A", text: "Any recent long travel or immobility?", is_correct: true, is_harmful: false, feedback: null, reveal: "Yes, a 14-hour flight yesterday." },
        { key: "B", text: "Does she take any hormonal medication?", is_correct: true, is_harmful: false, feedback: null, reveal: "A combined oral contraceptive pill." },
        { key: "C", text: "Did she have asthma as a child?", is_correct: false, is_harmful: false, feedback: "Low yield for an acute presentation like this one.", reveal: "No." },
      ],
      accepted_answers: [],
    },
    {
      stage: "differential",
      prompt: "Which diagnoses do you keep open?",
      explanation: "Sudden pleuritic pain with hypoxia needs pulmonary embolism and pneumothorax ruled in or out first.",
      options: [
        { key: "A", text: "Pulmonary embolism", is_correct: true, is_harmful: false, feedback: null, reveal: null },
        { key: "B", text: "Pneumothorax", is_correct: true, is_harmful: false, feedback: null, reveal: null },
        { key: "C", text: "Gastro-oesophageal reflux", is_correct: false, is_harmful: false, feedback: "Does not explain hypoxia or tachycardia.", reveal: null },
      ],
      accepted_answers: [],
    },
    {
      stage: "workup",
      prompt: "Which tests do you order first?",
      explanation: "With a high clinical probability, go straight to CT pulmonary angiography; D-dimer supports but cannot exclude.",
      options: [
        { key: "A", text: "CT pulmonary angiography", is_correct: true, is_harmful: false, feedback: null, reveal: "Filling defect in the right lower lobe pulmonary artery." },
        { key: "B", text: "D-dimer", is_correct: true, is_harmful: false, feedback: null, reveal: "2.4 mg/L FEU (raised)." },
        { key: "C", text: "Spirometry", is_correct: false, is_harmful: false, feedback: "Not useful in the acute setting.", reveal: "Not performed." },
      ],
      accepted_answers: [],
    },
    {
      stage: "diagnosis",
      prompt: "What is your diagnosis?",
      explanation: "Risk factors, a swollen calf, hypoxia and a CTPA filling defect confirm an acute pulmonary embolism.",
      options: [],
      accepted_answers: ["Pulmonary embolism", "PE", "Pulmonary thromboembolism"],
    },
    {
      stage: "treatment",
      prompt: "What is your initial plan?",
      explanation: "Haemodynamically stable PE: anticoagulate and remove the provoking factor.",
      options: [
        { key: "A", text: "Start anticoagulation (apixaban or LMWH)", is_correct: true, is_harmful: false, feedback: null, reveal: null },
        { key: "B", text: "Stop the combined oral contraceptive", is_correct: true, is_harmful: false, feedback: null, reveal: null },
        { key: "C", text: "Systemic thrombolysis", is_correct: false, is_harmful: true, feedback: "Thrombolysis is reserved for high-risk (massive) PE; in a stable patient the bleeding risk outweighs the benefit.", reveal: null },
      ],
      accepted_answers: [],
    },
  ],
  source: { kind: "llm", provider: "gemini", model: "gemini-3.8-flash", prompt_version: "v1" },
};

/** Offsets are computed from the quote, the same way the backend's grounding step does it (exact match here). */
function span(path: string, quote: string): EvidenceSpan {
  const start = quote ? EXTRACT_SOURCE.indexOf(quote) : -1;
  return start < 0
    ? { path, quote, start: null, end: null, grounded: false }
    : { path, quote, start, end: start + quote.length, grounded: true };
}

const EXTRACT_SPANS: EvidenceSpan[] = [
  span("chief_complaint", "sudden shortness of breath and sharp right-sided chest pain"),
  ...(EXTRACTED_CASE.findings ?? []).map((f, i) => span(`findings[${i}]`, f.evidence ?? "")),
  ...(EXTRACTED_CASE.measurements ?? []).map((m, i) => span(`measurements[${i}]`, m.evidence ?? "")),
  span("final_diagnosis", "acute pulmonary embolism"),
];

export const extractResponse: ExtractResponse = {
  case: EXTRACTED_CASE,
  source_text: EXTRACT_SOURCE,
  spans: EXTRACT_SPANS,
  phi: [
    { label: "NAME", count: 1 },
    { label: "DATE", count: 1 },
    { label: "PHONE", count: 1 },
  ],
  grounded_ratio: EXTRACT_SPANS.filter((s) => s.grounded).length / EXTRACT_SPANS.length,
  warnings: ["findings[5]: the quoted evidence was not found in the source text"],
  provider: "gemini",
  model: "gemini-3.8-flash",
  prompt_version: "v1",
  usage: { input_tokens: 2412, output_tokens: 1388, cost_usd: 0.007, latency_ms: 6840 },
};

export const caseCreated: CaseCreated = { id: peCasePublic.id, slug: peCasePublic.slug, created: false };
