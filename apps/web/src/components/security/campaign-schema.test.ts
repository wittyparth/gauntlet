import { describe, expect, it } from "vitest";

import type { Attack } from "@/lib/api/hooks/attacks";

import { benignSuites, campaignSchema, confirmationMatches, filterAttacks, isNarrowed, parseAttackIds, sourceFamily, unknownAttackIds } from "./campaign-schema";

const a = (id: string, category: string, vector: string, source: string, title = id) =>
  ({ id, category, vector, source, title, technique: "t" }) as unknown as Attack;
const lib = [
  a("1", "jailbreak", "user_turn", "garak@x:1"),
  a("2", "jailbreak", "document", "promptfoo@y:2"),
  a("3", "tool_injection", "user_turn", "garak@x:3", "SQL echo"),
];

describe("campaign form helpers", () => {
  it("derives the source family", () => expect(sourceFamily("promptfoo@0d49:sql-injection#7")).toBe("promptfoo"));
  it("filters by category, vector, source and text", () => {
    const base = { categories: ["jailbreak", "tool_injection"], vector: "all", source: "all", q: "" };
    expect(filterAttacks(lib, base)).toHaveLength(3);
    expect(filterAttacks(lib, { ...base, categories: ["jailbreak"] })).toHaveLength(2);
    expect(filterAttacks(lib, { ...base, vector: "document" }).map((x) => x.id)).toEqual(["2"]);
    expect(filterAttacks(lib, { ...base, source: "garak" })).toHaveLength(2);
    expect(filterAttacks(lib, { ...base, q: "sql" }).map((x) => x.id)).toEqual(["3"]);
  });
  it("knows when the library is narrowed beyond categories", () => {
    expect(isNarrowed({ categories: ["x"], vector: "all", source: "all", q: "" })).toBe(false);
    expect(isNarrowed({ categories: ["x"], vector: "document", source: "all", q: "" })).toBe(true);
  });
  it("validates the form", () => {
    const ok = { version_id: "v", suite_id: "s", categories: ["c"], repetitions: 1, max_attacks: 10, budget_dollars: 2 };
    expect(campaignSchema.safeParse(ok).success).toBe(true);
    expect(campaignSchema.safeParse({ ...ok, categories: [] }).success).toBe(false);
    expect(campaignSchema.safeParse({ ...ok, budget_dollars: 0 }).success).toBe(false);
  });
  it("requires the agent name as confirmation", () => {
    expect(confirmationMatches(" DVA SQL agent ", "DVA SQL agent")).toBe(true);
    expect(confirmationMatches("dva", "DVA SQL agent")).toBe(false);
  });
  it("offers only benign suites of the version's world", () => {
    const suites = [
      { id: "a", scenarios: ["s1"] },
      { id: "b", scenarios: ["s2"] },
      { id: "suite_campaign_x", scenarios: ["s1"] },
    ];
    const scenarios = [
      { id: "s1", scenario: { world: "w1" } },
      { id: "s2", scenario: { world: { id: "w2" } } },
    ];
    expect(benignSuites(suites, scenarios, "w1").map((s) => s.id)).toEqual(["a"]);
    expect(benignSuites(suites, scenarios, "w2").map((s) => s.id)).toEqual(["b"]);
  });
});

describe("advanced attack ids", () => {
  it("splits on commas and whitespace and dedupes", () => {
    expect(parseAttackIds("a1, a2\na1  a3,")).toEqual(["a1", "a2", "a3"]);
    expect(parseAttackIds("  ")).toEqual([]);
  });
  it("finds ids missing from the library", () => {
    expect(unknownAttackIds(["a1", "zz"], [{ id: "a1" } as never])).toEqual(["zz"]);
  });
});
