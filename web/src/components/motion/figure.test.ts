import { describe, expect, it } from "vitest";
import { formatFigure, parseFigure } from "./figure";

describe("parseFigure", () => {
  it("splits plain figures into prefix, number and suffix", () => {
    expect(parseFigure("0.912")).toEqual({ prefix: "", value: 0.912, decimals: 3, grouped: false, suffix: "" });
    expect(parseFigure("98%")).toEqual({ prefix: "", value: 98, decimals: 0, grouped: false, suffix: "%" });
    expect(parseFigure("$0.031")).toEqual({ prefix: "$", value: 0.031, decimals: 3, grouped: false, suffix: "" });
    expect(parseFigure("1,204")).toEqual({ prefix: "", value: 1204, decimals: 0, grouped: true, suffix: "" });
    expect(parseFigure(" 78 ")).toEqual({ prefix: "", value: 78, decimals: 0, grouped: false, suffix: "" });
  });

  it("leaves dashes, signed values and compound figures alone", () => {
    for (const text of ["—", "", "+0.02", "−4%", "-3", "3 of 5", "120 / 340 ms", "n/a"]) {
      expect(parseFigure(text)).toBeNull();
    }
  });
});

describe("formatFigure", () => {
  it("lands exactly on the original text at the end value", () => {
    for (const text of ["0.912", "98%", "0.4%", "$0.031", "1,204", "62%", "204"]) {
      const figure = parseFigure(text);
      expect(figure).not.toBeNull();
      expect(formatFigure(figure!, figure!.value)).toBe(text);
    }
  });

  it("keeps decimals, grouping and affixes while counting", () => {
    expect(formatFigure(parseFigure("0.912")!, 0)).toBe("0.000");
    expect(formatFigure(parseFigure("1,204")!, 999.6)).toBe("1,000");
    expect(formatFigure(parseFigure("$0.031")!, 0.0154)).toBe("$0.015");
  });
});
