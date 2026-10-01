import { describe, expect, it } from "vitest";
import { benchmarkX, buildCurve, CURVE } from "./curve";

const HISTOGRAM = [
  { points: 0, count: 18 },
  { points: 1, count: 47 },
  { points: 2, count: 96 },
  { points: 3, count: 51 },
];

/** Every SVG command here takes x,y pairs, so odd positions are y values. */
function ys(path: string): number[] {
  const nums = path.match(/-?\d+(\.\d+)?/g)?.map(Number) ?? [];
  return nums.filter((_, i) => i % 2 === 1);
}

describe("buildCurve", () => {
  it("puts the marker on your bin at the bin's height", () => {
    // 4 bins + one padding step each side: step = 480 / 5 = 96, bin 2 sits at 20 + 96 * 3.
    expect(buildCurve(HISTOGRAM, 3, 2).marker).toEqual({ x: 308, y: CURVE.top });
  });

  it("starts and ends on the baseline", () => {
    const { line, area } = buildCurve(HISTOGRAM, 3, 2);
    expect(line.startsWith(`M${CURVE.left} ${CURVE.base}`)).toBe(true);
    expect(line.endsWith(`${CURVE.right} ${CURVE.base}`)).toBe(true);
    expect(area.endsWith("Z")).toBe(true);
  });

  it("never dips below the baseline or above the ceiling", () => {
    for (const y of ys(buildCurve([{ points: 1, count: 40 }], 3, 0).line)) {
      expect(y).toBeLessThanOrEqual(CURVE.base);
      expect(y).toBeGreaterThanOrEqual(CURVE.ceiling);
    }
  });

  it("draws an empty histogram as a flat line", () => {
    const geo = buildCurve([], 3, 1);
    expect(new Set(ys(geo.line))).toEqual(new Set([CURVE.base]));
    expect(geo.marker.y).toBe(CURVE.base);
  });

  it("clamps your points into range and survives max_points 0", () => {
    expect(buildCurve(HISTOGRAM, 3, 9).marker.x).toBe(404);
    expect(buildCurve([{ points: 0, count: 5 }], 0, 0).marker).toEqual({ x: 180, y: CURVE.top });
  });
});

// C1 delta (amendments §E): the percentile card plots AI benchmark markers at the same x
// position a histogram bin for that point value would use, independent of bin heights.
describe("benchmarkX", () => {
  it("matches buildCurve's own bin placement for the same points", () => {
    expect(benchmarkX(3, 2)).toBe(308);
    expect(benchmarkX(3, 0)).toBe(116);
  });

  it("clamps out-of-range points and survives max_points 0", () => {
    expect(benchmarkX(3, 9)).toBe(404);
    expect(benchmarkX(0, 0)).toBe(180);
  });
});
