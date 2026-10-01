"use client";

import { useId, useRef, type RefObject } from "react";
import { prepareCountUp } from "@/components/motion/count-up";
import { gsap, MOTION_OK, ScrollTrigger, useGSAP } from "@/components/motion/gsap";
import type { AttemptResult } from "@/lib/api/types";
import { formatPercentile, modelLabel, pluralize } from "@/lib/format";
import { benchmarkX, buildCurve, CURVE } from "./curve";

/**
 * Plays once the card is on screen (it sits below the debrief on phones): the number counts up, the
 * cohort curve draws itself, the shaded area fades in, the "you" marker drops onto the curve, then
 * each AI player's marker pops in together with its label.
 */
function usePercentileTimeline(scope: RefObject<HTMLElement | null>) {
  useGSAP(
    () => {
      const el = scope.current;
      if (!el) return;
      const find = (selector: string) => gsap.utils.toArray<HTMLElement>(selector, el);
      const mm = gsap.matchMedia();
      mm.add(MOTION_OK, () => {
        const tl = gsap.timeline({ paused: true, defaults: { duration: 0.6, ease: "power3.out" } });
        tl.from(el, { opacity: 0, y: 16, duration: 0.7 }, 0);
        const numberEl = el.querySelector<HTMLElement>("[data-pct]");
        const count = numberEl ? prepareCountUp(numberEl, { paused: false, duration: 1 }) : null;
        if (count) tl.add(count.tween, 0.15);
        const line = el.querySelector("[data-curve-line]");
        if (line) tl.fromTo(line, { strokeDasharray: "1 1", strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 1.1, ease: "power2.inOut" }, 0.15);
        tl.from(find("[data-curve-area]"), { opacity: 0, duration: 0.7, ease: "power2.out", stagger: 0.15 }, 0.55)
          .from(find("[data-you]"), { y: -36, opacity: 0, duration: 0.75, ease: "back.out(1.4)" }, 1.0);
        const labels = find("[data-ai-label]");
        find("[data-ai-marker]").forEach((marker, i) => {
          const at = 1.45 + i * 0.22;
          tl.from(marker, { scale: 0, transformOrigin: "50% 50%", duration: 0.45, ease: "back.out(2.2)" }, at);
          if (labels[i]) tl.from(labels[i], { opacity: 0, y: 6, duration: 0.45 }, at + 0.05);
        });
        tl.from(find("[data-ai-note]"), { opacity: 0, duration: 0.5 }, ">-0.2");
        ScrollTrigger.create({ trigger: el, start: "top 88%", once: true, onEnter: () => void tl.play() });
        return () => count?.restore();
      });
    },
    { scope },
  );
}

export function PercentileCard({ result }: { result: AttemptResult }) {
  const titleId = useId();
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, ""); // safe inside url(#…)
  const scope = useRef<HTMLElement>(null);
  const pct = formatPercentile(result.percentile ?? null);
  usePercentileTimeline(scope);
  const geo = buildCurve(result.histogram, result.max_points, result.points);
  const { x, y } = geo.marker;
  const cohort = result.cohort_is_simulated ? "the simulated cohort on this case" : "physicians who worked this case";
  // C1 delta (amendments §E): AI models that played this case blinded, plotted at the same
  // x position a cohort bin for their point total would use.
  const benchmarks = result.benchmarks ?? [];

  return (
    <section
      ref={scope}
      data-percentile=""
      aria-labelledby={titleId}
      className="rounded-card border border-line bg-white px-5 pb-[18px] pt-6 shadow-lift sm:px-[26px]"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 id={titleId} className="text-[15px]">Your percentile</h3>
        <span className="font-mono text-[11.5px] text-muted">
          {pluralize(result.cohort_size, "attempt")} ·{" "}
          <span className="text-primary-hover">{result.cohort_is_simulated ? "simulated cohort" : "live cohort"}</span>
        </span>
      </div>

      {pct ? (
        <>
          <p className="mt-3.5 flex items-baseline gap-0.5 text-stat text-ink">
            <span aria-hidden="true" data-pct="">
              {pct.value}
            </span>
            <sup aria-hidden="true" className="text-[20px] font-medium">{pct.suffix}</sup>
            <span className="sr-only">{`${pct.value}${pct.suffix}`}</span>
            <small className="ml-2 text-sm2 font-normal tracking-normal text-muted">percentile</small>
          </p>
          <p className="mt-2 text-sm2 text-body">
            Ahead of <b className="font-semibold text-primary-hover">{pct.value}%</b> of {cohort}
          </p>
        </>
      ) : (
        <>
          <p className="mt-3.5 text-[22px] font-semibold tracking-[-.02em] text-ink">Too early to rank</p>
          <p className="mt-2 text-sm2 text-body">Percentile appears once 5 physicians have worked this case.</p>
        </>
      )}

      <svg
        viewBox="0 0 520 200"
        role="img"
        aria-label={`Distribution of points across ${pluralize(result.cohort_size, "attempt")}, with your ${result.points} of ${result.max_points} marked`}
        className="mt-1.5 h-auto w-full"
      >
        <defs>
          <linearGradient id={`${uid}-all`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" style={{ stopColor: "var(--color-primary)", stopOpacity: 0.1 }} />
            <stop offset="100%" style={{ stopColor: "var(--color-primary)", stopOpacity: 0 }} />
          </linearGradient>
          <linearGradient id={`${uid}-you`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" style={{ stopColor: "var(--color-primary)", stopOpacity: 0.3 }} />
            <stop offset="100%" style={{ stopColor: "var(--color-primary)", stopOpacity: 0.05 }} />
          </linearGradient>
          <clipPath id={`${uid}-ahead`}>
            <rect x={CURVE.left} y={CURVE.ceiling} width={Math.max(0, x - CURVE.left)} height={CURVE.base - CURVE.ceiling} />
          </clipPath>
        </defs>

        <line x1={CURVE.left} y1={CURVE.base} x2={CURVE.right} y2={CURVE.base} className="stroke-line" />
        {/* the whole cohort, then the part you are ahead of */}
        <path data-curve-area="" d={geo.area} fill={`url(#${uid}-all)`} />
        <path data-curve-area="" d={geo.area} fill={`url(#${uid}-you)`} clipPath={`url(#${uid}-ahead)`} />
        <path data-curve-line="" d={geo.line} pathLength={1} fill="none" strokeWidth={1.5} className="stroke-line-strong" />

        {benchmarks.map((b, i) => {
          const bx = benchmarkX(result.max_points, b.points);
          const by = CURVE.base - 9 - i * 11; // small stack so same-score models don't overlap
          return (
            <g key={b.label} data-ai-marker="" aria-label={`${modelLabel(b.model)}: ${b.points} of ${b.max_points} points, ${b.calibration}`} role="img">
              <rect x={bx - 3.5} y={by - 3.5} width={7} height={7} transform={`rotate(45 ${bx} ${by})`} className="fill-missed stroke-white" strokeWidth={1} />
            </g>
          );
        })}

        <g data-you="">
          <line x1={x} y1={y} x2={x} y2={CURVE.base + 6} strokeWidth={2} className="stroke-primary" />
          <circle cx={x} cy={y} r={5.5} fill="none" strokeWidth={1.5} className="halo animate-ping-soft stroke-primary" />
          <circle cx={x} cy={y} r={5.5} className="fill-primary" />
          <text x={x} y={y - 14} textAnchor="middle" className="fill-primary-hover font-mono text-[11.5px]">you</text>
        </g>

        <text x={CURVE.left} y={192} className="fill-muted font-mono text-[11px]">lower</text>
        <text x={260} y={192} textAnchor="middle" className="fill-muted font-mono text-[11px]">points in this case</text>
        <text x={CURVE.right} y={192} textAnchor="end" className="fill-muted font-mono text-[11px]">higher</text>
      </svg>

      {benchmarks.length > 0 ? (
        <ul className="mt-3 flex flex-wrap gap-1.5 border-t border-line pt-3">
          {benchmarks.map((b) => (
            <li
              key={b.label}
              data-ai-label=""
              className="inline-flex items-center gap-1.5 rounded-[6px] border border-missed-border bg-missed-tint px-[7px] py-1 font-mono text-[10.5px] text-missed-text"
            >
              <span aria-hidden="true" className="inline-block size-[6px] rotate-45 bg-missed" />
              {modelLabel(b.model)} · {b.points}/{b.max_points} · {b.calibration}
              {b.diagnosis_correct ? null : <span className="text-wrong"> · missed the diagnosis</span>}
            </li>
          ))}
        </ul>
      ) : null}
      {benchmarks.length > 0 ? (
        <p data-ai-note="" className="mt-2 text-[11px] text-muted">
          {pluralize(benchmarks.length, "model")} played this case blinded, the same way you did. They are markers on the chart, not
          part of the cohort distribution above.
        </p>
      ) : null}

      <div className="mt-3.5 flex flex-wrap justify-between gap-3 border-t border-line pt-[11px] font-mono text-[11px] text-muted">
        <span>{result.cohort_is_simulated ? "simulated distribution, labelled in the data" : "real attempts on this case"}</span>
        <span>updates after every attempt</span>
      </div>
    </section>
  );
}
