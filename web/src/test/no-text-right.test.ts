import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/*
 * `--color-right` (the debrief's "right" decision state) makes Tailwind v4 generate a `text-right`
 * COLOUR utility from our theme, which wins over Tailwind's own `text-right` text-align utility.
 * Any component that means "align this text to the end" and reaches for `text-right` therefore
 * renders teal — a "right" colour — on screen before a case closes, which breaks the product rule
 * that nothing is marked correct/incorrect until the debrief. Write `text-end` instead.
 */

const SRC_DIR = join(import.meta.dirname, "..");

const SELF = import.meta.filename;

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    const stat = statSync(path);
    if (stat.isDirectory()) out.push(...walk(path));
    else if (/\.(tsx?|jsx?)$/.test(entry) && path !== SELF) out.push(path);
  }
  return out;
}

describe("text-right token collision guard", () => {
  it("never uses the ambiguous `text-right` class (use `text-end`)", () => {
    const offenders: string[] = [];
    for (const file of walk(SRC_DIR)) {
      const text = readFileSync(file, "utf8");
      if (/\btext-right\b/.test(text)) offenders.push(file.replace(SRC_DIR, "src"));
    }
    expect(offenders).toEqual([]);
  });
});
