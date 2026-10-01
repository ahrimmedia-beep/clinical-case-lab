"use client";

import { useRef, type RefObject } from "react";
import { gsap, MOTION_OK, useGSAP } from "@/components/motion/gsap";

/*
 * Player motion stays quiet on purpose: a physician is working a case. No parallax, no colour, and
 * nothing that could read as right or wrong before the case closes.
 */

/** The new stage slides in from the side you are travelling to (14 px) while it fades in. */
export function useStageTransition(body: RefObject<HTMLElement | null>, index: number) {
  const previous = useRef(index);
  useGSAP(
    () => {
      const from = previous.current;
      previous.current = index;
      const el = body.current;
      if (!el || from === index || index < 0) return;
      const direction = index > from ? 1 : -1;
      const mm = gsap.matchMedia();
      mm.add(MOTION_OK, () => {
        gsap.from(el, { opacity: 0, x: 14 * direction, duration: 0.38, ease: "power2.out", clearProps: "opacity,transform" });
      });
    },
    { dependencies: [index], revertOnUpdate: true },
  );
}

/**
 * Confirms a lock-in: the chosen answers give one small scale pulse and the "Locked in." note fades
 * in. Scale only, same colours, so the pulse says "recorded", never "correct".
 */
export function useLockPulse(scope: RefObject<HTMLElement | null>, locked: boolean) {
  const wasLocked = useRef(locked);
  useGSAP(
    () => {
      const was = wasLocked.current;
      wasLocked.current = locked;
      const el = scope.current;
      if (!el || !locked || was) return;
      const mm = gsap.matchMedia();
      mm.add(MOTION_OK, () => {
        gsap
          .timeline()
          .to(gsap.utils.toArray<HTMLElement>('[aria-checked="true"], [data-lock-pulse]', el), {
            scale: 1.015,
            duration: 0.14,
            ease: "power2.out",
            yoyo: true,
            repeat: 1,
            clearProps: "transform",
          })
          .from(gsap.utils.toArray<HTMLElement>("[data-locked-note]", el), { opacity: 0, y: 4, duration: 0.3, ease: "power2.out", clearProps: "opacity,transform" }, 0.08);
      });
    },
    { dependencies: [locked], scope, revertOnUpdate: true },
  );
}
