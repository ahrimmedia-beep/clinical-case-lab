import { z } from "zod";
import type { FieldErrors } from "@/lib/action-states";
import type { AttemptIn, ExtractRequest, RevealIn } from "@/lib/api/types";
import { MULTI_SELECT_STAGES, REVEAL_STAGES } from "@/lib/api/types";

/** Server-side validation of everything a Server Action receives. Server Actions are public POST endpoints. */

export type ParseResult<T> = { ok: true; value: T } | { ok: false; fieldErrors: FieldErrors };

const SLUG = /^[a-z0-9-]{3,100}$/;

export function isValidSlug(slug: string): boolean {
  return SLUG.test(slug);
}

/** The end user's IP as Cloud Run's front end reports it (first X-Forwarded-For entry). */
export function clientIp(headers: { get(name: string): string | null }): string | null {
  const candidate = (headers.get("x-forwarded-for")?.split(",")[0] ?? headers.get("x-real-ip") ?? "").trim();
  return /^[0-9a-fA-F:.]{2,45}$/.test(candidate) ? candidate : null;
}

const optionKeys = z.array(z.string().regex(/^[A-L]$/, "Unknown option")).max(12, "Too many options");

const jsonChoices = z
  .string()
  .transform((raw, ctx) => {
    try {
      return JSON.parse(raw) as unknown;
    } catch {
      ctx.addIssue({ code: "custom", message: "Malformed answers" });
      return z.NEVER;
    }
  })
  .pipe(z.partialRecord(z.enum(MULTI_SELECT_STAGES), optionKeys));

const attemptForm = z.object({
  choices: jsonChoices,
  diagnosis_text: z
    .string()
    .trim()
    .min(1, "Write your diagnosis before closing the case.")
    .max(200, "Keep the diagnosis under 200 characters."),
  confidence: z.coerce
    .number()
    .int("Rate your confidence from 1 to 5.")
    .min(1, "Rate your confidence from 1 to 5.")
    .max(5, "Rate your confidence from 1 to 5."),
  duration_ms: z.coerce.number().int().min(0).max(3_600_000).nullable().catch(null),
});

export function parseAttemptForm(formData: FormData): ParseResult<AttemptIn> {
  const parsed = attemptForm.safeParse({
    choices: formData.get("choices") ?? "{}",
    diagnosis_text: formData.get("diagnosis_text") ?? "",
    confidence: formData.get("confidence") ?? "",
    duration_ms: formData.get("duration_ms") || null,
  });
  if (!parsed.success) return { ok: false, fieldErrors: z.flattenError(parsed.error).fieldErrors };

  const choices: AttemptIn["choices"] = {};
  for (const stage of MULTI_SELECT_STAGES) {
    const keys = parsed.data.choices[stage];
    if (keys && keys.length > 0) choices[stage] = [...new Set(keys)];
  }
  return {
    ok: true,
    value: {
      choices,
      diagnosis_text: parsed.data.diagnosis_text,
      confidence: parsed.data.confidence,
      duration_ms: parsed.data.duration_ms,
    },
  };
}

const extractForm = z.object({
  text: z
    .string()
    .trim()
    .min(50, "Paste at least 50 characters of clinical text.")
    .max(20_000, "Keep the text under 20,000 characters."),
  provider: z.enum(["gemini", "claude"], { error: "Choose Gemini or Claude." }),
});

export function parseExtractForm(formData: FormData): ParseResult<ExtractRequest> {
  const parsed = extractForm.safeParse({
    text: formData.get("text") ?? "",
    provider: formData.get("provider") ?? "gemini",
  });
  if (!parsed.success) return { ok: false, fieldErrors: z.flattenError(parsed.error).fieldErrors };
  return { ok: true, value: { text: parsed.data.text, provider: parsed.data.provider, model: null } };
}

const revealInput = z.object({
  slug: z.string().regex(SLUG),
  stage: z.enum(REVEAL_STAGES),
  keys: optionKeys.min(1, "Choose at least one option"),
});

export function parseRevealInput(slug: unknown, stage: unknown, keys: unknown): ParseResult<{ slug: string; body: RevealIn }> {
  const parsed = revealInput.safeParse({ slug, stage, keys });
  if (!parsed.success) return { ok: false, fieldErrors: z.flattenError(parsed.error).fieldErrors };
  return {
    ok: true,
    value: { slug: parsed.data.slug, body: { stage: parsed.data.stage, option_keys: [...new Set(parsed.data.keys)] } },
  };
}
