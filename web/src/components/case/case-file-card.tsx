import type { ReactNode } from "react";
import { Pill } from "@/components/ui/pill";
import type { Patient } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatMinutes, formatPatient, initials, stageNo } from "@/lib/format";

export type CaseFileHint = { label: string; hint: string };

type Props = {
  number: number;
  specialty: string;
  minutes: number;
  title: string;
  patient: Patient;
  difficulty: string;
  chiefComplaint: string;
  hints: CaseFileHint[];
  footer: ReactNode;
  titleAs?: "h1" | "h2" | "h3";
};

/**
 * The "Opening Case" card from eximion.com/pulmonology (screens/crops/pulm-opening-case.png).
 * No hooks, so it renders on the server (catalog) and inside the client player (intro).
 */
export function CaseFileCard({ number, specialty, minutes, title, patient, difficulty, chiefComplaint, hints, footer, titleAs: Title = "h3" }: Props) {
  return (
    <article className="relative flex h-full flex-col overflow-hidden rounded-card border border-line bg-white shadow-card before:absolute before:inset-x-0 before:top-0 before:h-1 before:bg-brand-grad">
      <header className="flex items-center justify-between gap-3 border-b border-line px-5 pb-3.5 pt-[18px]">
        <span className="inline-flex min-w-0 items-center gap-2 font-mono text-[11px] font-medium uppercase tracking-[.1em] text-primary">
          <span aria-hidden="true" className="size-[7px] flex-none rounded-full bg-primary" />
          <span className="truncate">
            Case {stageNo(number)} · {specialty}
          </span>
        </span>
        <Pill tone="time">{formatMinutes(minutes)}</Pill>
      </header>
      <div className="flex-1 px-5 pb-5 pt-[22px]">
        <div className="mb-[18px] flex items-start gap-3.5">
          <span
            aria-hidden="true"
            className="flex size-16 flex-none items-center justify-center rounded-[14px] bg-primary-tint text-[20px] font-semibold text-primary-deep sm:size-[84px] sm:text-[24px]"
          >
            {initials(patient.display_name)}
          </span>
          <div className="min-w-0">
            <Title className="text-[19px] leading-[1.25] tracking-[-.02em] [overflow-wrap:anywhere] sm:text-[21px]">{title}</Title>
            <p className="mt-1 text-[12.5px] text-muted">
              {formatPatient(patient)} · {difficulty}
            </p>
            <p className="mt-2 text-[14px] leading-normal text-body">{chiefComplaint}</p>
          </div>
        </div>
        {hints.length > 0 ? (
          <ul>
            {hints.map((h, i) => (
              <li key={h.label} className={cn("flex items-center gap-3 py-[11px]", i > 0 && "border-t border-line")}>
                <span aria-hidden="true" className="size-[9px] flex-none rounded-full border-2 border-primary" />
                <span className="text-[14px] font-medium text-body">{h.label}</span>
                <span className="ml-auto text-end text-[11.5px] text-muted">{h.hint}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <footer className="flex flex-wrap items-center gap-2.5 border-t border-line bg-surface-alt px-5 py-3.5 text-[12px] text-muted">{footer}</footer>
    </article>
  );
}
