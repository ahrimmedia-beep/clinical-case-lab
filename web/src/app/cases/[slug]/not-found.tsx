import Link from "next/link";
import { buttonClasses } from "@/components/ui/button";

export default function CaseNotFound() {
  return (
    <div className="mx-auto max-w-site px-4 py-24 sm:px-6">
      <p className="font-mono text-eyebrow uppercase text-primary-hover">Case not found</p>
      <h1 className="mt-3 text-[clamp(27px,3.1vw,38px)]">This case isn&apos;t in the library</h1>
      <p className="mt-4 max-w-[520px] text-lead">It may have been removed, or the link is incomplete.</p>
      <Link href="/cases" className={buttonClasses("primary", "mt-8")}>Browse cases</Link>
    </div>
  );
}
