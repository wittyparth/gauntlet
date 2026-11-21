import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import { MigrationTable } from "./migration-table";

const point = (over: Record<string, unknown>) => ({
  run_id: "r1", agent_version_id: "v1", label: "v1", model: null, pass_rate: 0.9, ci_low: 0.8, ci_high: 0.95,
  cost_per_episode_usd_micros: 1000, latency_p95_ms: 420, on_frontier: true, dominated_by: [], dominance_supported: false,
  ...over,
});

describe("MigrationTable", () => {
  it("shows p95 latency, n/a when missing, and frontier membership", () => {
    render(<MigrationTable points={[point({}), point({ run_id: "r2", label: "v2", latency_p95_ms: null, on_frontier: false })] as never} />);
    expect(screen.getByText("420 ms")).toBeTruthy();
    expect(screen.getByText("n/a")).toBeTruthy();
    expect(screen.getByText("on frontier")).toBeTruthy();
    expect(screen.getByText("dominated")).toBeTruthy();
  });
});
