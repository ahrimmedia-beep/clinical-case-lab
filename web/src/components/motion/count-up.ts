"use client";

import { formatFigure, parseFigure } from "./figure";
import { gsap } from "./gsap";

export type CountUp = { tween: gsap.core.Tween; restore: () => void };

/**
 * Prepares an element whose only child is a server-rendered figure ("0.912", "98%") to count up
 * from zero. Locks the element's width first so neighbours never shift while digits change (no
 * CLS), sets the zero state, and returns a paused tween plus `restore`, which puts the original
 * text back (call it from the matchMedia/useGSAP cleanup). Returns null for anything that is not
 * a single plain figure; that element simply stays as rendered.
 */
export function prepareCountUp(el: HTMLElement, vars: gsap.TweenVars = {}): CountUp | null {
  const text = el.firstChild;
  if (el.childNodes.length !== 1 || !(text instanceof Text)) return null;
  const final = text.data;
  const figure = parseFigure(final);
  if (!figure || figure.value === 0) return null;

  const width = el.getBoundingClientRect().width;
  const inline = getComputedStyle(el).display === "inline";
  gsap.set(el, inline ? { minWidth: width, display: "inline-block" } : { minWidth: width });

  const state = { value: 0 };
  text.data = formatFigure(figure, 0);
  const tween = gsap.to(state, {
    value: figure.value,
    duration: 1.1,
    ease: "power2.out",
    paused: true,
    ...vars,
    onUpdate: () => {
      text.data = formatFigure(figure, state.value);
    },
    onComplete: () => {
      text.data = final;
    },
  });
  return {
    tween,
    restore: () => {
      tween.kill();
      text.data = final;
    },
  };
}
