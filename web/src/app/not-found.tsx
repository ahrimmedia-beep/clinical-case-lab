import Link from "next/link";
import { buttonClasses } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-site px-4 py-24 sm:px-6">
      <p className="font-mono text-eyebrow uppercase text-primary-hover">404</p>
      <h1 className="mt-3 text-[clamp(27px,3.1vw,38px)]">This page isn&apos;t here</h1>
      <p className="mt-4 max-w-[520px] text-lead">The link may be old. The case library has everything that is live.</p>
      <Link href="/cases" className={buttonClasses("primary", "mt-8")}>Open the case library</Link>
    </div>
  );
}
