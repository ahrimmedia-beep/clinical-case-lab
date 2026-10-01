/** Geometry for the percentile card: a smooth curve through the points histogram, in a 520×200 viewBox. */

export const CURVE = { left: 20, right: 500, base: 170, top: 50, ceiling: 20 } as const;

type Point = { x: number; y: number };

const round = (n: number) => Math.round(n * 10) / 10;
const clampY = (y: number) => Math.min(CURVE.base, Math.max(CURVE.ceiling, y));

/** Catmull-Rom through every point, as cubic Béziers; control points are clamped so the fill never leaks below the axis. */
export function smoothPath(points: Point[]): string {
  if (points.length === 0) return "";
  let d = `M${round(points[0].x)} ${round(points[0].y)}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] ?? points[i];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2] ?? p2;
    const c1 = { x: p1.x + (p2.x - p0.x) / 6, y: clampY(p1.y + (p2.y - p0.y) / 6) };
    const c2 = { x: p2.x - (p3.x - p1.x) / 6, y: clampY(p2.y - (p3.y - p1.y) / 6) };
    d += ` C${round(c1.x)} ${round(c1.y)} ${round(c2.x)} ${round(c2.y)} ${round(p2.x)} ${round(p2.y)}`;
  }
  return d;
}

/** Where a bin for `points` (out of `maxPoints`) sits on the x-axis — the same formula buildCurve uses for its bins. */
function binX(maxPoints: number, points: number): number {
  const span = Math.max(1, Math.round(maxPoints));
  const step = (CURVE.right - CURVE.left) / (span + 2); // one empty step of padding on each side
  const p = Math.min(span, Math.max(0, Math.round(points)));
  return CURVE.left + step * (p + 1);
}

/**
 * C1 delta (amendments §E): x position for an AI benchmark marker. Benchmarks are single
 * attempts, not part of the cohort histogram, so they share the histogram's x-axis placement
 * but never affect its shape.
 */
export function benchmarkX(maxPoints: number, points: number): number {
  return round(binX(maxPoints, points));
}

export function buildCurve(
  histogram: readonly { points: number; count: number }[],
  maxPoints: number,
  yourPoints: number,
): { line: string; area: string; marker: Point } {
  const span = Math.max(1, Math.round(maxPoints));
  const counts = Array.from({ length: span + 1 }, (_, p) =>
    histogram.filter((bin) => bin.points === p).reduce((sum, bin) => sum + bin.count, 0),
  );
  const peak = Math.max(1, ...counts);
  const step = (CURVE.right - CURVE.left) / (span + 2); // one empty step of padding on each side
  const bins = counts.map((count, p) => ({
    x: CURVE.left + step * (p + 1),
    y: CURVE.base - (count / peak) * (CURVE.base - CURVE.top),
  }));
  const line = smoothPath([{ x: CURVE.left, y: CURVE.base }, ...bins, { x: CURVE.right, y: CURVE.base }]);
  const you = bins[Math.min(span, Math.max(0, Math.round(yourPoints)))];
  return {
    line,
    area: `${line} L${CURVE.right} ${CURVE.base} L${CURVE.left} ${CURVE.base} Z`,
    marker: { x: round(you.x), y: round(you.y) },
  };
}
