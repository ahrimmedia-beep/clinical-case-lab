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

export default async function RootLayout({ children }: { children: ReactNode }) {
  await connection(); // env is read per request, never baked in at build time
  return (
    <html lang="en" className={`${poppins.variable} ${plexMono.variable}`}>
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
