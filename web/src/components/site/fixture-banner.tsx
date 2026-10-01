import { connection } from "next/server";
import { isFixtureMode } from "@/lib/env";

/** Makes fixture mode impossible to miss, so a deploy without API_BASE_URL never passes for the real thing. */
export async function FixtureBanner() {
  await connection();
  if (!isFixtureMode()) return null;
  return (
    <div role="status" className="border-b border-line bg-surface-alt px-4 py-2 text-center font-mono text-[11.5px] text-muted">
      Fixture mode: API_BASE_URL is not set, so pages show built-in sample data.
    </div>
  );
}
