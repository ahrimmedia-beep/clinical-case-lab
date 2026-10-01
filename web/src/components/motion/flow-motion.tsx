"use client";

import { useRef, type ReactNode } from "react";
import { gsap, markReady, MOTION_OK, ScrollTrigger, useGSAP } from "./gsap";

/**
 * The "note → debrief" flow draws itself as it scrolls through: the rail line grows from the first
 * step to the last, each node lights up as the line reaches it, and its step card rises in.
 * Markup (server-rendered, complete without JS): `data-flow-line="x"` (horizontal rail, from 1024
 * px), `data-flow-line="y"` (vertical rail, below 640 px), `data-flow-node` and `data-flow-step`
 * in step order. Between 640 and 1023 px there is no rail; the steps just rise in.
 * Scrubbed, never pinned, so it cannot trap scrolling on a phone.
 */
export function FlowMotion({ children, className }: { children: ReactNode; className?: string }) {
  const root = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const el = root.current;
      if (!el) return;
      const find = (selector: string) => gsap.utils.toArray<HTMLElement>(selector, el);
      const mm = gsap.matchMedia();

      mm.add({ motion: MOTION_OK, wide: "(min-width: 1024px)", narrow: "(max-width: 639px)" }, (context) => {
        const { motion, wide, narrow } = context.conditions ?? {};
        if (!motion) return;
        const steps = find("[data-flow-step]");

        if (!wide && !narrow) {
          gsap.set(steps, { autoAlpha: 0, y: 14 });
          ScrollTrigger.batch(steps, {
            start: "top 92%",
            once: true,
            onEnter: (batch) => gsap.to(batch, { autoAlpha: 1, y: 0, duration: 0.6, ease: "power3.out", stagger: 0.08, overwrite: true }),
          });
          return;
        }

        const line = find(wide ? '[data-flow-line="x"]' : '[data-flow-line="y"]');
        const nodes = find("[data-flow-node]");
        gsap.set(line, wide ? { scaleX: 0, transformOrigin: "left center" } : { scaleY: 0, transformOrigin: "center top" });
        gsap.set(nodes, { scale: 0, transformOrigin: "50% 50%" });
        gsap.set(steps, { autoAlpha: 0, y: wide ? 16 : 10 });

        // One time unit per gap between steps: node i is reached at time i.
        const gaps = Math.max(1, steps.length - 1);
        const tl = gsap.timeline({
          // Desktop: one row, so the whole draw fits while it travels from 85 % to 48 % of the
          // viewport and every step is shown before the row reaches the middle. Phones: a column,
          // each step lights up as it enters the lower part of the screen.
          scrollTrigger: { trigger: el, start: wide ? "top 85%" : "top 88%", end: wide ? "top 48%" : "bottom 72%", scrub: 0.6 },
        });
        tl.to(line, wide ? { scaleX: 1, duration: gaps, ease: "none" } : { scaleY: 1, duration: gaps, ease: "none" }, 0);
        steps.forEach((step, i) => {
          if (nodes[i]) tl.to(nodes[i], { scale: 1, duration: 0.3, ease: "back.out(2.4)" }, i);
          tl.to(step, { autoAlpha: 1, y: 0, duration: 0.7, ease: "power2.out" }, Math.max(0, i - 0.15));
        });
      });

      markReady(el);
    },
    { scope: root },
  );

  return (
    <div ref={root} data-motion="" className={className}>
      {children}
    </div>
  );
}
