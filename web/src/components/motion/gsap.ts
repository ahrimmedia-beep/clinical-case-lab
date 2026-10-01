"use client";

/*
 * The one place GSAP is registered. Every motion component imports from here, so ScrollTrigger and
 * the useGSAP hook are registered once per bundle. Plugins used on a single route (SplitText on the
 * landing) are registered in that route's component instead, to keep them out of the other pages.
 *
 * Motion contract for the whole app:
 *  - Server-rendered HTML is the final state. Initial "from" states are set by GSAP on the client.
 *  - Before a motion root hydrates, its animated parts are hidden by a CSS gate (globals.css) that
 *    only exists while JS is running: an inline script in the root layout sets
 *    `html[data-motion-pending]` and removes it after a 2.5 s failsafe, so content never stays
 *    hidden if the bundle fails to load. Each root sets `data-motion-ready` once its states are set.
 *  - prefers-reduced-motion: reduce → nothing is hidden and nothing moves (gsap.matchMedia).
 *  - Pointer effects only on fine pointers with hover, from 1024 px; scroll effects are lighter
 *    on small screens; nothing is pinned.
 */

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(useGSAP, ScrollTrigger);

if (typeof window !== "undefined") {
  // next/font swaps the web font in after first paint; trigger positions depend on text height.
  void document.fonts?.ready.then(() => ScrollTrigger.refresh());
}

/** Media queries shared by every motion component. */
export const MOTION_OK = "(prefers-reduced-motion: no-preference)";
/** Desktop-class pointer: pointer parallax and card tilt only run here. */
export const FINE_POINTER = "(hover: hover) and (pointer: fine) and (min-width: 1024px)";
/** Phones get shorter travel and lighter scroll effects. */
export const SMALL_SCREEN = "(max-width: 768px)";

export function isSmallScreen(): boolean {
  return window.matchMedia(SMALL_SCREEN).matches;
}

/** Lifts the CSS gate for this root: its initial states are set, GSAP owns the rest. */
export function markReady(root: Element | null): void {
  root?.setAttribute("data-motion-ready", "");
}

export { gsap, ScrollTrigger, useGSAP };
