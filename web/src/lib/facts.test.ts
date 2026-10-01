import { describe, expect, it } from "vitest";
import { extractResponse } from "@/lib/api/fixtures";
import { economics, factRows, finishedSteps, groundingFor, phiSummary, runningSteps } from "./facts";

describe("facts", () => {
  it("lists every extracted item with the path the evidence spans use", () => {
    const rows = factRows(extractResponse.case);
    expect(rows.map((r) => r.path)).toEqual([
      "patient", "chief_complaint",
      "findings[0]", "findings[1]", "findings[2]", "findings[3]", "findings[4]", "findings[5]",
      "measurements[0]", "measurements[1]", "measurements[2]",
      "final_diagnosis", "differential[0]",
    ]);
    expect(rows.find((r) => r.path === "patient")?.text).toBe("34-year-old woman");
    expect(rows.find((r) => r.path === "measurements[0]")?.text).toBe("Heart rate 112 bpm (high)");
    expect(rows.find((r) => r.path === "final_diagnosis")?.text).toBe("Pulmonary embolism (I26.99)");
  });

  it("survives a case without optional lists or age", () => {
    const bare = { ...extractResponse.case, findings: undefined, measurements: undefined, differential: undefined, patient: { sex: "unknown" as const } };
    expect(factRows(bare).map((r) => r.path)).toEqual(["patient", "chief_complaint", "final_diagnosis"]);
  });

  it("classifies grounding per item", () => {
    expect(groundingFor("findings[0]", extractResponse.spans)).toBe("grounded");
    expect(groundingFor("findings[5]", extractResponse.spans)).toBe("ungrounded");
    expect(groundingFor("patient", extractResponse.spans)).toBe("none");
  });

  it("summarises masked identifiers", () => {
    expect(phiSummary([{ label: "NAME", count: 1 }, { label: "DATE", count: 2 }, { label: "MRN", count: 2 }, { label: "EMAIL", count: 0 }])).toBe(
      "1 name · 2 dates · 2 MRNs",
    );
    expect(phiSummary([])).toBe("none found");
  });
});

describe("studio economics and steps", () => {
  it("reads the draft's time, cost and grounding off the response", () => {
    expect(economics(extractResponse)).toEqual({ draftTime: "6.8 s", cost: "$0.007", grounded: 10, quoted: 11, groundedLabel: "10/11" });
    expect(economics({ ...extractResponse, usage: { ...extractResponse.usage, latency_ms: 23_600, cost_usd: 0.0214 } })).toMatchObject({
      draftTime: "24 s",
      cost: "$0.021",
    });
  });

  it("estimates the running step from elapsed time and never finishes on its own", () => {
    const states = (ms: number) => runningSteps(ms).map((s) => s.state);
    expect(states(0)).toEqual(["running", "waiting", "waiting", "waiting", "waiting"]);
    expect(states(5_000)).toEqual(["done", "running", "waiting", "waiting", "waiting"]);
    expect(states(20_000)).toEqual(["done", "done", "done", "running", "waiting"]);
    expect(states(600_000)).toEqual(["done", "done", "done", "done", "running"]);
  });

  it("reports what each step produced and flags grounding misses and warnings", () => {
    const steps = finishedSteps(extractResponse);
    expect(steps.map((s) => [s.key, s.state])).toEqual([
      ["deidentify", "done"],
      ["extract", "done"],
      ["ground", "warn"],
      ["author", "done"],
      ["validate", "warn"],
    ]);
    expect(steps[0].detail).toBe("1 name · 1 date · 1 phone masked");
    expect(steps[2].detail).toBe("10/11 quotes found in the text");
    expect(steps[3].detail).toBe("5 decision points");
    expect(steps[4].detail).toBe("1 warning to check");
  });
});
