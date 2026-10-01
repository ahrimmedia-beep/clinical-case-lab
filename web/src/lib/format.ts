/** Small, pure formatters shared by server and client components. */

export function stageNo(n: number): string {
  return String(n).padStart(2, "0");
}

export function ordinalSuffix(n: number): "st" | "nd" | "rd" | "th" {
  const v = Math.abs(Math.trunc(n));
  const mod100 = v % 100;
  if (mod100 >= 11 && mod100 <= 13) return "th";
  switch (v % 10) {
    case 1:
      return "st";
    case 2:
      return "nd";
    case 3:
      return "rd";
    default:
      return "th";
  }
}

export function formatPercentile(p: number | null): { value: number; suffix: string } | null {
  if (p === null || Number.isNaN(p)) return null;
  const value = Math.min(100, Math.max(0, Math.round(p)));
  return { value, suffix: ordinalSuffix(value) };
}

export function formatRatio(r: number | null | undefined, digits = 0): string {
  if (r === null || r === undefined || Number.isNaN(r)) return "—";
  return `${(r * 100).toFixed(digits)}%`;
}

export function formatScore(r: number | null | undefined): string {
  if (r === null || r === undefined || Number.isNaN(r)) return "—";
  return r.toFixed(2);
}

export function formatInt(n: number): string {
  return Math.round(n).toLocaleString("en-US");
}

export function formatUsd(v: number): string {
  if (v === 0) return "$0";
  if (v >= 1) return `$${v.toFixed(2)}`;
  return `$${String(Number(v.toPrecision(2)))}`;
}

export function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function formatMinutes(n: number): string {
  return `~${n} min`;
}

export function formatPickRate(r: number | null | undefined): string | null {
  if (r === null || r === undefined || Number.isNaN(r)) return null;
  return `${Math.round(r * 100)}% of peers chose this`;
}

export function formatPatient(p: { age_years: number | null; sex: string }): string {
  const child = p.age_years !== null && p.age_years < 18;
  const noun =
    p.sex === "female" ? (child ? "girl" : "woman") : p.sex === "male" ? (child ? "boy" : "man") : child ? "child" : "patient";
  if (p.age_years === null) return `${noun[0].toUpperCase()}${noun.slice(1)}, age not given`;
  return `${p.age_years}-year-old ${noun}`;
}

export function initials(name: string | null | undefined): string {
  const cleaned = (name ?? "").replace(/^\s*(mr|mrs|ms|mx|miss|dr)\.?\s+/i, "").trim();
  const letters = cleaned
    .split(/\s+/)
    .map((word) => word.match(/[A-Za-z]/)?.[0] ?? "")
    .filter(Boolean);
  return letters.length > 0 ? letters.slice(0, 2).join("").toUpperCase() : "Pt";
}

export function pluralize(n: number, one: string, many?: string): string {
  return `${n} ${n === 1 ? one : (many ?? `${one}s`)}`;
}

/** "claude-sonnet-5-5" → "Claude Sonnet 5.5"; "gemini-3.8-flash" → "Gemini 3.8 Flash". */
export function modelLabel(model: string): string {
  const tokens = model.split("@")[0].split("-").filter(Boolean);
  const out: string[] = [];
  for (const token of tokens) {
    const prev = out[out.length - 1];
    if (/^\d+$/.test(token) && prev !== undefined && /^\d+$/.test(prev)) {
      out[out.length - 1] = `${prev}.${token}`;
    } else {
      out.push(/^\d/.test(token) ? token : `${token[0].toUpperCase()}${token.slice(1)}`);
    }
  }
  return out.join(" ");
}

export function modelKey(m: { provider: string; model: string }): string {
  return `${m.provider}/${m.model}`;
}
