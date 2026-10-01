import { describe, expect, it } from "vitest";
import { toSegments, type Segment } from "./highlight";

const TEXT = "abcdefghij";

const span = (path: string, start: number | null, end: number | null, grounded = true) => ({ path, start, end, grounded });
const shape = (segments: Segment[]) => segments.map((s) => [s.text, s.paths]);

describe("toSegments", () => {
  it("returns the whole text as one plain segment when there are no spans", () => {
    expect(shape(toSegments(TEXT, []))).toEqual([["abcdefghij", []]]);
  });

  it("cuts a single span out of the middle", () => {
    expect(shape(toSegments(TEXT, [span("a", 2, 5)]))).toEqual([["ab", []], ["cde", ["a"]], ["fghij", []]]);
  });

  it("splits overlapping spans into shared and single parts", () => {
    expect(shape(toSegments(TEXT, [span("a", 1, 5), span("b", 3, 8)]))).toEqual([
      ["a", []],
      ["bc", ["a"]],
      ["de", ["a", "b"]],
      ["fgh", ["b"]],
      ["ij", []],
    ]);
  });

  it("keeps a nested span inside its parent", () => {
    expect(shape(toSegments(TEXT, [span("outer", 0, 10), span("inner", 4, 6)]))).toEqual([
      ["abcd", ["outer"]],
      ["ef", ["outer", "inner"]],
      ["ghij", ["outer"]],
    ]);
  });

  it("ignores ungrounded, null, empty, reversed and negative spans", () => {
    const segments = toSegments(TEXT, [span("u", 2, 4, false), span("n", null, null), span("e", 3, 3), span("r", 6, 2), span("neg", -2, 3)]);
    expect(shape(segments)).toEqual([["abcdefghij", []]]);
  });

  it("clamps a span that runs past the end and drops one that starts past it", () => {
    expect(shape(toSegments(TEXT, [span("a", 7, 99), span("b", 12, 15)]))).toEqual([["abcdefg", []], ["hij", ["a"]]]);
  });

  it("de-duplicates identical spans and merges touching spans of the same path", () => {
    expect(shape(toSegments(TEXT, [span("a", 2, 4), span("a", 2, 4), span("a", 4, 6)]))).toEqual([
      ["ab", []],
      ["cdef", ["a"]],
      ["ghij", []],
    ]);
  });

  it("always reassembles the original text with contiguous offsets", () => {
    const segments = toSegments(TEXT, [span("a", 0, 3), span("b", 2, 9), span("c", 9, 10), span("d", 5, 5)]);
    expect(segments.map((s) => s.text).join("")).toBe(TEXT);
    segments.forEach((s, i) => expect(s.start).toBe(i === 0 ? 0 : segments[i - 1].end));
  });

  it("returns nothing for empty text", () => {
    expect(toSegments("", [span("a", 0, 3)])).toEqual([]);
  });
});
