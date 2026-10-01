"use client";

import { useRef, type ReactNode } from "react";
import { prepareCountUp } from "./count-up";
import { FINE_POINTER, gsap, isSmallScreen, markReady, MOTION_OK, ScrollTrigger, useGSAP } from "./gsap";

type Props = { children: ReactNode; className?: string; tilt?: boolean };

/**
 * Scroll-driven entrances for server-rendered content. Wrap a page or section; mark its children:
 *
 *   data-reveal         fades and rises in when scrolled into view, batched with its neighbours
 *   data-reveal="fade"  fades only (table rows and cells, where a transform is not wanted)
 *   data-bar            a horizontal bar that grows from 0 to its rendered width
 *   data-count          a figure that counts up to its rendered text
 *   data-tilt           (with `tilt`) leans toward a fine pointer; a `data-tilt-shadow` child fades in
 *
 * Everything runs once; the server HTML is the final state and reduced motion keeps it as is.
 * Entrances animate opacity, never visibility, so a link that has not faded in yet can still take
 * keyboard focus (focus scrolls it into view, which reveals it).
 */
export function Reveal({ children, className, tilt = false }: Props) {
  const root = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const el = root.current;
      if (!el) return;
      const mm = gsap.matchMedia();

      mm.add(MOTION_OK, () => {
        const small = isSmallScreen();
        const find = (selector: string) => gsap.utils.toArray<HTMLElement>(selector, el);

        const items = find("[data-reveal]");
        if (items.length > 0) {
          // Fade back to each element's own CSS opacity (a dimmed table row stays dimmed).
          const natural = new Map(items.map((item) => [item, Number(getComputedStyle(item).opacity)]));
          gsap.set(items, { opacity: 0, y: (_: number, t: HTMLElement) => (t.dataset.reveal === "fade" ? 0 : small ? 12 : 20) });
          ScrollTrigger.batch(items, {
            start: "top 92%",
            once: true,
            onEnter: (batch) =>
              gsap.to(batch, {
                opacity: (_: number, t: HTMLElement) => natural.get(t) ?? 1,
                y: 0,
                duration: small ? 0.55 : 0.75,
                ease: "power3.out",
                stagger: Math.min(0.08, 0.7 / batch.length),
                overwrite: true,
              }),
          });
        }

        const bars = find("[data-bar]");
        if (bars.length > 0) {
          gsap.set(bars, { scaleX: 0, transformOrigin: "left center" });
          ScrollTrigger.batch(bars, {
            start: "top 94%",
            once: true,
            onEnter: (batch) =>
              gsap.to(batch, { scaleX: 1, duration: 0.9, ease: "power3.out", delay: 0.15, stagger: Math.min(0.05, 0.6 / batch.length), overwrite: true }),
          });
        }

        const restores: (() => void)[] = [];
        for (const node of find("[data-count]")) {
          const count = prepareCountUp(node);
          if (!count) continue;
          restores.push(count.restore);
          ScrollTrigger.create({ trigger: node, start: "top 92%", once: true, onEnter: () => void count.tween.play() });
        }
        return () => restores.forEach((restore) => restore());
      });

      if (tilt) {
        mm.add(`${MOTION_OK} and ${FINE_POINTER}`, () => {
          const cleanups = gsap.utils.toArray<HTMLElement>("[data-tilt]", el).map((card) => {
            const shadow = card.querySelector<HTMLElement>("[data-tilt-shadow]");
            gsap.set(card, { transformPerspective: 1000, transformOrigin: "50% 50%" });
            const ease = { duration: 0.5, ease: "power3.out" };
            const rotateX = gsap.quickTo(card, "rotationX", ease);
            const rotateY = gsap.quickTo(card, "rotationY", ease);
            const lift = gsap.quickTo(card, "y", ease);
            const glow = shadow ? gsap.quickTo(shadow, "opacity", { duration: 0.35, ease: "power2.out" }) : null;
            let box: DOMRect | null = null;

            const enter = () => {
              box = card.getBoundingClientRect();
              lift(-4);
              glow?.(1);
            };
            const move = (event: PointerEvent) => {
              box ??= card.getBoundingClientRect();
              const px = (event.clientX - box.left) / box.width - 0.5;
              const py = (event.clientY - box.top) / box.height - 0.5;
              rotateY(gsap.utils.clamp(-0.5, 0.5, px) * 5);
              rotateX(gsap.utils.clamp(-0.5, 0.5, py) * -4);
            };
            const leave = () => {
              box = null;
              rotateX(0);
              rotateY(0);
              lift(0);
              glow?.(0);
            };
            card.addEventListener("pointerenter", enter);
            card.addEventListener("pointermove", move);
            card.addEventListener("pointerleave", leave);
            return () => {
              card.removeEventListener("pointerenter", enter);
              card.removeEventListener("pointermove", move);
              card.removeEventListener("pointerleave", leave);
            };
          });
          return () => cleanups.forEach((cleanup) => cleanup());
        });
      }

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
