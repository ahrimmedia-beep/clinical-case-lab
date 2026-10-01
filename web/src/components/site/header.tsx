import Link from "next/link";
import { GITHUB_URL } from "@/lib/links";
import { cn } from "@/lib/cn";

const NAV = [
  { href: "/cases", label: "Cases" },
  { href: "/studio", label: "Studio" },
  { href: "/evals", label: "Evals" },
] as const;

const NAV_LINK =
  "relative py-1 hover:text-ink after:absolute after:bottom-0 after:left-0 after:h-[1.5px] after:w-0 after:bg-primary after:transition-[width] hover:after:w-full";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-line bg-white/88 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-site items-center gap-4 px-4 sm:px-6 md:h-[70px] md:gap-9">
        <Link href="/" className="flex items-center gap-2.5" aria-label="Case Lab, home">
          <span className="text-[16px] font-semibold uppercase leading-none tracking-[.17em] text-ink sm:text-[18px]">Case Lab</span>
          <span className="hidden rounded-full border border-line px-2.5 py-1 font-mono text-[10px] tracking-[.08em] text-muted sm:inline-block">
            Take-home · Eximion
          </span>
        </Link>
        <nav aria-label="Main" className="ml-auto flex items-center gap-4 text-[13.5px] text-body sm:gap-[26px] sm:text-[14px]">
          {NAV.map((item) => (
            <Link key={item.href} href={item.href} className={NAV_LINK}>
              {item.label}
            </Link>
          ))}
          <a href={GITHUB_URL} target="_blank" rel="noreferrer" className={cn(NAV_LINK, "hidden md:inline-block")}>
            GitHub
          </a>
        </nav>
      </div>
    </header>
  );
}
