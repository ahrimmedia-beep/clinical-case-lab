import type { Metadata } from "next";
import { connection } from "next/server";
import type { ReactNode } from "react";
import { SiteFooter } from "@/components/site/footer";
import { FixtureBanner } from "@/components/site/fixture-banner";
import { SiteHeader } from "@/components/site/header";
import { apiDocsUrl } from "@/lib/env";
import { plexMono, poppins } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Case Lab", template: "%s · Case Lab" },
  description: "Clinical cases end to end: LLM extraction with verbatim evidence, a case player with server-side scoring, debrief and percentile.",
};

/* Runs before first paint: arms the motion gate in globals.css, and disarms it after 2.5 s whatever
   happens, so a failed bundle can never leave content hidden. */
const MOTION_GATE = `(function(d){d.setAttribute("data-motion-pending","");setTimeout(function(){d.removeAttribute("data-motion-pending")},2500)})(document.documentElement)`;

export default async function RootLayout({ children }: { children: ReactNode }) {
  await connection(); // env is read per request, never baked in at build time
  return (
    // suppressHydrationWarning: the inline gate script adds an attribute to <html> before hydration.
    <html lang="en" className={`${poppins.variable} ${plexMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: MOTION_GATE }} />
      </head>
      <body className="flex min-h-dvh flex-col bg-surface font-sans text-copy text-body antialiased">
        <a
          href="#main"
          className="sr-only rounded-btn bg-white px-4 py-2 text-ink focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60]"
        >
          Skip to content
        </a>
        <FixtureBanner />
        <SiteHeader />
        <main id="main" className="flex-1">
          {children}
        </main>
        <SiteFooter apiDocsUrl={apiDocsUrl()} />
      </body>
    </html>
  );
}
