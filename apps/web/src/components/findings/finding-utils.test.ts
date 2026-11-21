import { describe, expect, it } from "vitest";

import { heatStep, hostCovered, reproText, sortFindings, targetHost } from "./finding-utils";

describe("finding utils", () => {
  it("sorts by severity then newest", () => {
    const rows = [
      { id: "a", severity: "high", created_at: "2026-01-01" },
      { id: "b", severity: "critical", created_at: "2025-01-01" },
      { id: "c", severity: "high", created_at: "2026-02-01" },
    ];
    expect(sortFindings(rows).map((r) => r.id)).toEqual(["b", "c", "a"]);
  });
  it("formats reproducibility", () => expect(reproText([7, 10])).toBe("7/10"));
  it("reads the host of a remote target", () => {
    expect(targetHost({ kind: "openai_compat", base_url: "https://Api.Example.com/v1" })).toBe("api.example.com");
    expect(targetHost({ kind: "hosted" })).toBeNull();
  });
  it("covers subdomains of a verified host", () => {
    expect(hostCovered("api.example.com", ["example.com"])).toBe(true);
    expect(hostCovered("badexample.com", ["example.com"])).toBe(false);
  });
  it("bands the heat scale and keeps untested apart from zero", () => {
    expect(heatStep(0, 0)).toBe(0);
    expect(heatStep(4, 0)).toBe(1);
    expect(heatStep(4, 1)).toBe(2);
    expect(heatStep(4, 2)).toBe(3);
    expect(heatStep(4, 3)).toBe(4);
    expect(heatStep(4, 4)).toBe(5);
  });
});
