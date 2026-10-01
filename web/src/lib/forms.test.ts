import { describe, expect, it } from "vitest";
import { clientIp, isValidSlug, parseAttemptForm, parseExtractForm, parsePublishInput, parseRevealInput } from "./forms";

function form(fields: Record<string, string>): FormData {
  const fd = new FormData();
  for (const [key, value] of Object.entries(fields)) fd.set(key, value);
  return fd;
}

const valid = {
  choices: JSON.stringify({ workup: ["B", "A", "A"], interview: [] }),
  diagnosis_text: "  Pulmonary embolism ",
  confidence: "4",
  duration_ms: "61000",
};

describe("parseAttemptForm", () => {
  it("accepts a complete attempt, trims text, de-duplicates keys and drops empty stages", () => {
    expect(parseAttemptForm(form(valid))).toEqual({
      ok: true,
      value: { choices: { workup: ["B", "A"] }, diagnosis_text: "Pulmonary embolism", confidence: 4, duration_ms: 61000 },
    });
  });

  it("treats a missing duration as null", () => {
    const result = parseAttemptForm(form({ ...valid, duration_ms: "" }));
    expect(result.ok && result.value.duration_ms).toBeNull();
  });

  it("asks for a diagnosis and a confidence", () => {
    const result = parseAttemptForm(form({ ...valid, diagnosis_text: "   ", confidence: "" }));
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.fieldErrors.diagnosis_text?.[0]).toBe("Write your diagnosis before closing the case.");
      expect(result.fieldErrors.confidence?.[0]).toBe("Rate your confidence from 1 to 5.");
    }
  });

  it("rejects out-of-range confidence, unknown stages, bad keys and malformed JSON", () => {
    expect(parseAttemptForm(form({ ...valid, confidence: "7" })).ok).toBe(false);
    expect(parseAttemptForm(form({ ...valid, choices: JSON.stringify({ diagnosis: ["A"] }) })).ok).toBe(false);
    expect(parseAttemptForm(form({ ...valid, choices: JSON.stringify({ workup: ["Z9"] }) })).ok).toBe(false);
    const broken = parseAttemptForm(form({ ...valid, choices: "{not json" }));
    expect(broken.ok).toBe(false);
    if (!broken.ok) expect(broken.fieldErrors.choices?.[0]).toBe("Malformed answers");
  });
});

describe("parseExtractForm", () => {
  it("accepts 50+ characters and a known provider; the server picks the model", () => {
    expect(parseExtractForm(form({ text: "x".repeat(60), provider: "claude" }))).toEqual({
      ok: true,
      value: { text: "x".repeat(60), provider: "claude", model: null },
    });
  });

  it("explains short text and unknown providers", () => {
    const result = parseExtractForm(form({ text: "too short", provider: "openai" }));
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.fieldErrors.text?.[0]).toBe("Paste at least 50 characters of clinical text.");
      expect(result.fieldErrors.provider?.[0]).toBe("Choose Gemini or Claude.");
    }
  });
});

describe("reveals and slugs", () => {
  it("validates reveal requests", () => {
    expect(parseRevealInput("sudden-breathlessness-3f9a1c", "workup", ["A", "B", "A"])).toEqual({
      ok: true,
      value: { slug: "sudden-breathlessness-3f9a1c", body: { stage: "workup", option_keys: ["A", "B"] } },
    });
    expect(parseRevealInput("sudden-breathlessness-3f9a1c", "treatment", ["A"]).ok).toBe(false);
    expect(parseRevealInput("Bad Slug!", "workup", ["A"]).ok).toBe(false);
    expect(parseRevealInput("ok-slug", "workup", []).ok).toBe(false);
  });

  it("accepts only API-shaped slugs", () => {
    expect(isValidSlug("layout-stress-test")).toBe(true);
    expect(isValidSlug("ab")).toBe(false);
    expect(isValidSlug("../etc/passwd")).toBe(false);
  });

  it("takes the end user's IP from the last X-Forwarded-For entry (Cloud Run appends the real peer)", () => {
    expect(clientIp(new Headers({ "x-forwarded-for": "10.9.8.7, 203.0.113.7" }))).toBe("203.0.113.7");
    expect(clientIp(new Headers({ "x-forwarded-for": "203.0.113.7" }))).toBe("203.0.113.7");
    expect(clientIp(new Headers({ "x-forwarded-for": "spoofed, 203.0.113.7 " }))).toBe("203.0.113.7");
    expect(clientIp(new Headers({ "x-real-ip": "2001:db8::1" }))).toBe("2001:db8::1");
    expect(clientIp(new Headers({ "x-forwarded-for": "<script>" }))).toBeNull();
    expect(clientIp(new Headers())).toBeNull();
  });
});

describe("parsePublishInput", () => {
  const text = "x".repeat(60);

  it("accepts what the studio extracted: text, provider and the model that ran", () => {
    expect(parsePublishInput({ text: `  ${text} `, provider: "claude", model: "claude-sonnet-5" })).toEqual({
      ok: true,
      value: { text, provider: "claude", model: "claude-sonnet-5" },
    });
    expect(parsePublishInput({ text, provider: "gemini", model: null })).toEqual({ ok: true, value: { text, provider: "gemini", model: null } });
  });

  it("refuses anything else, including a whole case sent in place of the text", () => {
    expect(parsePublishInput(null).ok).toBe(false);
    expect(parsePublishInput("{}").ok).toBe(false);
    expect(parsePublishInput({ text: "short", provider: "gemini", model: null }).ok).toBe(false);
    expect(parsePublishInput({ text, provider: "openai", model: null }).ok).toBe(false);
    expect(parsePublishInput({ text, provider: "gemini", model: "bad model!" }).ok).toBe(false);
    expect(parsePublishInput({ text, provider: "gemini", model: null, case: { title: "x" } }).ok).toBe(false);
  });
});
