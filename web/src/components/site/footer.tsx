import Link from "next/link";
import { GITHUB_URL } from "@/lib/links";

const COL = "font-mono text-[11.5px] font-medium uppercase tracking-[.12em] text-ink";

export function SiteFooter({ apiDocsUrl }: { apiDocsUrl: string | null }) {
  return (
    <footer className="border-t border-line bg-surface-alt pb-10 pt-16 text-[14px] text-muted">
      <div className="mx-auto grid max-w-site gap-10 px-4 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr]">
        <div>
          <p className="text-[15px] font-semibold uppercase tracking-[.17em] text-ink">Case Lab</p>
          <p className="mt-3 max-w-[360px]">
            Clinical cases end to end: raw text, grounded extraction, a case player with server-side scoring.
          </p>
          <span className="mt-4 inline-block rounded-full border border-line px-2.5 py-1 font-mono text-[10px] tracking-[.08em]">
            Take-home · Eximion
          </span>
        </div>
        <div>
          <h2 className={COL}>Build</h2>
          <ul className="mt-3 space-y-2">
            <li>
              <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="hover:text-ink">Source on GitHub</a>
            </li>
            {apiDocsUrl ? (
              <li>
                <a href={apiDocsUrl} target="_blank" rel="noreferrer" className="hover:text-ink">API docs (OpenAPI)</a>
              </li>
            ) : null}
            <li>
              <Link href="/evals" className="hover:text-ink">Eval report</Link>
            </li>
          </ul>
        </div>
        <div>
          <h2 className={COL}>Data</h2>
          <p className="mt-3">Synthetic cases only. Please don&apos;t paste real patient data into the studio.</p>
        </div>
      </div>
      <div className="mx-auto mt-12 flex max-w-site flex-wrap justify-between gap-3 px-4 font-mono text-[11.5px] sm:px-6">
        <span>Built as a take-home for Eximion. Not an Eximion product.</span>
        <span>ahrimmedia-beep · 2026</span>
      </div>
    </footer>
  );
}
