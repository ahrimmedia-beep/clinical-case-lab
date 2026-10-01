/** Turns evidence spans (possibly overlapping, possibly bad) into flat segments for rendering. Pure. */

export type SpanLike = { path: string; start?: number | null; end?: number | null; grounded: boolean };
export type Segment = { start: number; end: number; text: string; paths: string[] };

type Valid = { path: string; start: number; end: number };

export function toSegments(text: string, spans: readonly SpanLike[]): Segment[] {
  if (text.length === 0) return [];

  const valid: Valid[] = [];
  for (const s of spans) {
    if (!s.grounded || typeof s.start !== "number" || typeof s.end !== "number") continue;
    if (!Number.isInteger(s.start) || !Number.isInteger(s.end)) continue;
    if (s.start < 0 || s.start >= text.length || s.end <= s.start) continue;
    valid.push({ path: s.path, start: s.start, end: Math.min(s.end, text.length) });
  }

  const cuts = new Set<number>([0, text.length]);
  for (const s of valid) {
    cuts.add(s.start);
    cuts.add(s.end);
  }
  const points = [...cuts].sort((a, b) => a - b);

  const segments: Segment[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const start = points[i];
    const end = points[i + 1];
    const paths = [...new Set(valid.filter((s) => s.start <= start && s.end >= end).map((s) => s.path))];
    const prev = segments[segments.length - 1];
    if (prev && sameSet(prev.paths, paths)) {
      prev.end = end;
      prev.text = text.slice(prev.start, end);
    } else {
      segments.push({ start, end, text: text.slice(start, end), paths });
    }
  }
  return segments;
}

function sameSet(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((p) => b.includes(p));
}
