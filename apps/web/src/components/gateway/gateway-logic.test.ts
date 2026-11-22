import { describe, expect, it } from "vitest";

import { parseCheck } from "./check-validation";
import { confirmSummary, needsConfirm } from "./mode-logic";

describe("parseCheck", () => {
  it("accepts a known check", () => {
    const r = parseCheck('{"type":"tool_called","tool":"issue_refund"}');
    expect(r.ok).toBe(true);
  });
  it("accepts nested checks and flags an unknown nested type", () => {
    expect(parseCheck('{"type":"all","of":[{"type":"tool_called","tool":"a"}]}').ok).toBe(true);
    const bad = parseCheck('{"type":"all","of":[{"type":"made_up"}]}');
    expect(bad.ok).toBe(false);
  });
  it("rejects an unknown type", () => {
    const r = parseCheck('{"type":"nope"}');
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.message).toContain("nope");
  });
  it("reports the position of a JSON syntax error", () => {
    const r = parseCheck('{"type": tool_called}');
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.message).toMatch(/JSON/);
  });
  it("rejects non-objects", () => {
    expect(parseCheck("[1]").ok).toBe(false);
    expect(parseCheck("3").ok).toBe(false);
  });
});

describe("mode confirmation", () => {
  const cur = { mode: "shadow", fail: "open" } as const;
  it("asks for shadow to enforce and open to closed only", () => {
    expect(needsConfirm(cur, { mode: "enforce", fail: "open" })).toBe(true);
    expect(needsConfirm(cur, { mode: "shadow", fail: "closed" })).toBe(true);
    expect(needsConfirm({ mode: "enforce", fail: "closed" }, { mode: "shadow", fail: "open" })).toBe(false);
    expect(needsConfirm(cur, cur)).toBe(false);
  });
  it("shows the numbers or the untested warning", () => {
    expect(confirmSummary(null).tested).toBe(false);
    const s = confirmSummary({ block_rate: 0.92, fp_rate: 0.03 } as never);
    expect(s.tested && s.text).toContain("92%");
  });
});
