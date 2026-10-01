"use client";

import { SplitText } from "gsap/SplitText";
import { useRef, type ReactNode } from "react";
import { FINE_POINTER, gsap, isSmallScreen, markReady, MOTION_OK, useGSAP } from "./gsap";

gsap.registerPlugin(SplitText); // landing only, so it stays out of the other routes' bundles

/*
 * Layers, back to front. `data-depth` is the extra vertical travel in px while the hero scrolls
 * out (positive = lags behind, reads as far away); `data-pointer` is the travel in px toward a
 * fine pointer (negative = away from it). Each layer is a stack: depth wrapper → pointer wrapper →
 * intro visual, so the three motions never fight over the same transform.
 */

type Props = { copy: ReactNode; aside: ReactNode };

export function HeroMotion({ copy, aside }: Props) {
  const root = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      const el = root.current;
      if (!el) return;
      const find = (selector: string) => gsap.utils.toArray<HTMLElement>(selector, el);
      const mm = gsap.matchMedia();

      // Entrance: glow, then the headline word by word, the copy, the case card, the case files behind it.
      mm.add(MOTION_OK, () => {
        const title = el.querySelector<HTMLElement>("[data-split]");
        const split = title ? SplitText.create(title, { type: "words" }) : null;
        const tl = gsap.timeline({ defaults: { duration: 0.8, ease: "power3.out" } });
        tl.from(find('[data-intro="glow"]'), { autoAlpha: 0, duration: 1.8, ease: "power2.out" }, 0)
          .from(find('[data-intro="lead"]'), { autoAlpha: 0, y: 10 }, 0.05);
        if (split) {
          tl.from(
            split.words,
            { autoAlpha: 0, yPercent: 42, duration: 0.95, ease: "expo.out", stagger: 0.075, onComplete: () => void split.revert() },
            0.14,
          );
        }
        tl.from(find('[data-intro="copy"]'), { autoAlpha: 0, y: 14, stagger: 0.08 }, 0.42)
          .from(find('[data-intro="card"]'), { autoAlpha: 0, y: 30, duration: 1.1 }, 0.28)
          .from(find('[data-intro="ghost"]'), { autoAlpha: 0, y: 26, scale: 0.96, duration: 1.2, stagger: 0.14 }, 0.55);
      });

      // Scroll parallax: layers drift apart as the hero leaves. Half the travel on phones.
      mm.add(MOTION_OK, () => {
        const scale = isSmallScreen() ? 0.5 : 1;
        const tl = gsap.timeline({
          defaults: { ease: "none" },
          scrollTrigger: { trigger: el, start: "top top", end: "bottom top", scrub: 0.5 },
        });
        for (const layer of find("[data-depth]")) tl.to(layer, { y: Number(layer.dataset.depth) * scale }, 0);
      });

      // Pointer parallax: desktop with a mouse only.
      mm.add(`${MOTION_OK} and ${FINE_POINTER}`, () => {
        const layers = find("[data-pointer]").map((node) => ({
          x: gsap.quickTo(node, "x", { duration: 0.9, ease: "power3.out" }),
          y: gsap.quickTo(node, "y", { duration: 0.9, ease: "power3.out" }),
          travel: Number(node.dataset.pointer),
        }));
        let box: DOMRect | null = null;
        const move = (event: PointerEvent) => {
          box ??= el.getBoundingClientRect();
          const nx = gsap.utils.clamp(-0.5, 0.5, (event.clientX - box.left) / box.width - 0.5);
          const ny = gsap.utils.clamp(-0.5, 0.5, (event.clientY - box.top) / box.height - 0.5);
          for (const layer of layers) {
            layer.x(nx * layer.travel);
            layer.y(ny * layer.travel);
          }
        };
        const reset = () => {
          box = null;
          for (const layer of layers) {
            layer.x(0);
            layer.y(0);
          }
        };
        const forget = () => (box = null); // the hero moved: measure again on the next move
        el.addEventListener("pointermove", move);
        el.addEventListener("pointerleave", reset);
        window.addEventListener("scroll", forget, { passive: true });
        return () => {
          el.removeEventListener("pointermove", move);
          el.removeEventListener("pointerleave", reset);
          window.removeEventListener("scroll", forget);
        };
      });

      markReady(el);
    },
    { scope: root },
  );

  return (
    <section ref={root} data-motion="" className="relative isolate overflow-hidden bg-hero-grad text-hero-text">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
        <div data-depth="70" className="absolute inset-0 will-change-transform">
          <div
            data-pointer="-4"
            className="absolute -inset-x-3 inset-y-0 bg-hairline-grid opacity-60 [mask-image:radial-gradient(120%_80%_at_30%_0%,black_35%,transparent_100%)]"
          />
        </div>
        <div data-depth="110" className="absolute -left-[14%] -top-[38%] will-change-transform">
          <div data-pointer="18">
            <div
              data-intro="glow"
              className="size-[min(78vw,760px)] rounded-full bg-[radial-gradient(closest-side,rgba(95,214,198,.17),rgba(95,214,198,0))]"
            />
          </div>
        </div>
        <div data-depth="-40" className="absolute -right-[12%] top-[30%] will-change-transform">
          <div data-pointer="-14">
            <div
              data-intro="glow"
              className="size-[min(64vw,600px)] rounded-full bg-[radial-gradient(closest-side,rgba(3,166,150,.20),rgba(3,166,150,0))]"
            />
          </div>
        </div>
      </div>

      <div className="mx-auto grid max-w-site gap-12 px-4 py-[clamp(56px,8vw,112px)] sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:items-center">
        <div>{copy}</div>
        <div className="relative">
          <div aria-hidden="true" className="pointer-events-none absolute inset-0 hidden lg:block">
            <div data-depth="36" className="absolute -left-11 top-[24%] will-change-transform">
              <div data-pointer="-12">
                <div data-intro="ghost">
                  <GhostFile />
                </div>
              </div>
            </div>
            <div data-depth="8" className="absolute -right-6 -top-16 will-change-transform">
              <div data-pointer="-7">
                <div data-intro="ghost">
                  <GhostDebrief />
                </div>
              </div>
            </div>
            <div data-depth="-24" className="absolute -bottom-14 -left-10 will-change-transform">
              <div data-pointer="9">
                <div data-intro="ghost">
                  <GhostCurve />
                </div>
              </div>
            </div>
          </div>
          <div data-depth="-48" className="relative z-10 will-change-transform">
            <div data-pointer="5">
              <div data-intro="card">{aside}</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* Decorative case files floating behind the hero card: glass on the dark ground, no real data. */

const GHOST = "rounded-[14px] border border-white/[.13] bg-white/[.05] p-3.5 shadow-on-dark";
const GHOST_LABEL = "flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[.14em] text-primary-lit/80";

function GhostFile() {
  return (
    <div className={`${GHOST} w-[200px] -rotate-[7deg]`}>
      <p className={GHOST_LABEL}>
        <span className="size-[5px] rounded-full bg-primary-lit/80" />
        Case file
      </p>
      <div className="mt-3 flex gap-2.5">
        <span className="size-9 flex-none rounded-[9px] bg-white/10" />
        <span className="flex-1 space-y-1.5 pt-1">
          <i className="block h-[5px] w-4/5 rounded-full bg-white/20" />
          <i className="block h-[5px] w-1/2 rounded-full bg-white/10" />
        </span>
      </div>
      <ul className="mt-3 space-y-2 border-t border-white/10 pt-2.5">
        {["w-3/4", "w-2/3", "w-4/5"].map((w) => (
          <li key={w} className="flex items-center gap-2">
            <span className="size-[6px] flex-none rounded-full border border-primary-lit/60" />
            <i className={`block h-[4px] ${w} rounded-full bg-white/12`} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function GhostDebrief() {
  return (
    <div className={`${GHOST} w-[230px] rotate-[5deg]`}>
      <p className={GHOST_LABEL}>Debrief</p>
      <p className="mt-2 text-[22px] font-semibold leading-none tracking-[-.03em] text-white/70">
        6<span className="text-white/35">/8</span>
      </p>
      <span className="mt-3 flex h-[6px] gap-[3px]">
        <i className="block rounded-bar bg-primary-lit/70" style={{ flex: 6 }} />
        <i className="block rounded-bar bg-wrong/70" style={{ flex: 2 }} />
        <i className="block rounded-bar bg-missed/70" style={{ flex: 1 }} />
      </span>
      <ul className="mt-3 space-y-2">
        {[5, 3, 4].map((n, i) => (
          <li key={i} className="flex items-center gap-2">
            <i className="block h-[4px] flex-1 rounded-full bg-white/12" />
            <span className="flex h-[4px] w-14 gap-[2px]">
              <i className="block rounded-full bg-primary-lit/60" style={{ flex: n }} />
              <i className="block rounded-full bg-white/15" style={{ flex: 6 - n }} />
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function GhostCurve() {
  return (
    <div className={`${GHOST} w-[220px] -rotate-[4deg]`}>
      <p className={GHOST_LABEL}>Percentile</p>
      <svg viewBox="0 0 190 64" className="mt-2 h-auto w-full">
        <path d="M4 58 C40 58 52 14 92 12 C130 10 146 58 186 58 Z" className="fill-primary-lit/10" />
        <path d="M4 58 C40 58 52 14 92 12 C130 10 146 58 186 58" fill="none" strokeWidth={1.4} className="stroke-primary-lit/70" />
        <line x1={129} y1={27} x2={129} y2={60} strokeWidth={1.4} className="stroke-primary-lit" />
        <circle cx={129} cy={27} r={3.6} className="fill-primary-lit" />
        <line x1={4} y1={60.5} x2={186} y2={60.5} strokeWidth={1} className="stroke-white/15" />
      </svg>
    </div>
  );
}
