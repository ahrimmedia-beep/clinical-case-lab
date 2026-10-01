import type { Metadata } from "next";
import { connection } from "next/server";
import { StudioClient } from "@/components/studio/studio-client";
import { Eyebrow } from "@/components/ui/eyebrow";
import { STUDIO_SAMPLES } from "@/data/studio-samples";

export const metadata: Metadata = {
  title: "Studio",
  description: "Turn a clinical note into a draft case: de-identify, extract with verbatim quotes, check every quote, author the decisions.",
};

export default async function StudioPage() {
  await connection();
  return (
    <div className="mx-auto max-w-site px-4 py-[clamp(48px,7vw,96px)] sm:px-6">
      <header className="mb-10 max-w-head">
        <Eyebrow>Studio</Eyebrow>
        <h1 className="mt-3 text-[clamp(27px,3.1vw,38px)]">Turn a clinical note into a draft case</h1>
        <p className="mt-4 text-lead">
          Paste a note or pick a sample. Identifiers are masked first; the model extracts each fact with a verbatim quote, every quote is checked
          against the text, and a second pass writes the decisions. The result is a draft that a physician reviews before anyone plays it.
        </p>
      </header>
      <StudioClient samples={STUDIO_SAMPLES} />
    </div>
  );
}
