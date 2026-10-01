/**
 * A displayed figure ("0.912", "98%", "$0.031", "1,204", "78") split so it can count up from zero
 * and land on exactly the text the server rendered. Anything that is not one plain, unsigned
 * number (a dash, "+0.02", "3 of 5", "120 / 340 ms") is left alone.
 */
export type Figure = { prefix: string; value: number; decimals: number; grouped: boolean; suffix: string };

const FIGURE = /^([^\d+\-−±]*)(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?([^\d]*)$/;

export function parseFigure(text: string): Figure | null {
  const match = FIGURE.exec(text.trim());
  if (!match) return null;
  const [, prefix, whole, fraction = "", suffix] = match;
  const value = Number(`${whole.replace(/,/g, "")}${fraction ? `.${fraction}` : ""}`);
  if (!Number.isFinite(value)) return null;
  return { prefix, value, decimals: fraction.length, grouped: whole.includes(","), suffix };
}

export function formatFigure(figure: Figure, value: number): string {
  const n = figure.grouped
    ? value.toLocaleString("en-US", { minimumFractionDigits: figure.decimals, maximumFractionDigits: figure.decimals })
    : value.toFixed(figure.decimals);
  return `${figure.prefix}${n}${figure.suffix}`;
}
