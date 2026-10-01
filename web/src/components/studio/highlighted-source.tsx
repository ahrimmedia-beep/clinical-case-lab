"use client";

import { useMemo } from "react";
import type { EvidenceSpan } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { toSegments } from "@/lib/highlight";

const PLACEHOLDER = /(\[[A-Z_]+_\d+\])/g; // [NAME_1], [PHONE_2], … from the de-identification step

function PlainText({ text }: { text: string }) {
  return (
    <>
      {text.split(PLACEHOLDER).map((part, i) =>
        i % 2 === 1 ? (
          <span key={i} title="Masked before the model saw the text" className="rounded-[3px] border border-dashed border-line-strong px-0.5 text-muted">
            {part}
          </span>
        ) : (
          part
        ),
      )}
    </>
  );
}

type Props = { text: string; spans: EvidenceSpan[]; active: string | null; onActive: (path: string | null) => void };

/** The de-identified source with every grounded quote highlighted; overlaps get a deeper tint. */
export function HighlightedSource({ text, spans, active, onActive }: Props) {
  const segments = useMemo(() => toSegments(text, spans), [text, spans]);
  return (
    <p className="whitespace-pre-wrap font-mono text-[13px] leading-[1.8] text-body [overflow-wrap:anywhere]">
      {segments.map((seg) =>
        seg.paths.length === 0 ? (
          <PlainText key={seg.start} text={seg.text} />
        ) : (
          <mark
            key={seg.start}
            data-paths={seg.paths.join(" ")}
            onMouseEnter={() => onActive(seg.paths[0])}
            onMouseLeave={() => onActive(null)}
            className={cn(
              "rounded-[3px] px-px text-ink transition-colors",
              active !== null && seg.paths.includes(active)
                ? "bg-primary/30 ring-1 ring-primary"
                : seg.paths.length > 1
                  ? "bg-primary/20"
                  : "bg-primary-tint",
            )}
          >
            <PlainText text={seg.text} />
          </mark>
        ),
      )}
    </p>
  );
}
