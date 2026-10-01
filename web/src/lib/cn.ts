/** Joins class names. Variants are written so they never conflict, so no merge step is needed. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
