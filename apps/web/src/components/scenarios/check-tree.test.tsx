import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CheckTree } from "./check-tree";
import { describeCheck } from "./describe-check";

describe("describeCheck", () => {
  it("summarises tool_called with count and args", () => {
    const d = describeCheck({
      type: "tool_called",
      tool: "issue_refund",
      count: { min: 2 },
      args: { amount_cents: { lte: 4800, ref_op: "eq" } },
    });
    expect(d.summary).toBe("issue_refund called at least 2 with amount_cents lte 4800");
  });
  it("summarises state, state_diff and output leaves", () => {
    expect(
      describeCheck({ type: "state", collection: "orders", id: "ord_1", path: "total_cents", matcher: { eq: 12000 } })
        .summary,
    ).toBe("orders:ord_1 total_cents eq 12000");
    expect(describeCheck({ type: "state_diff", collection: "orders", added: { min: 1, max: 1 } }).summary).toBe(
      "orders: added exactly 1",
    );
    expect(describeCheck({ type: "output", matcher: { regex: "(?i)expired" }, scope: "any" }).summary).toBe(
      "agent output (any) matches /(?i)expired/",
    );
  });
  it("marks unknown types as not known", () => {
    expect(describeCheck({ type: "telepathy" }).known).toBe(false);
    expect(describeCheck("nope").known).toBe(false);
  });
});

describe("CheckTree", () => {
  it("renders nested all > not > tool_called", () => {
    render(
      <CheckTree
        check={{
          type: "all",
          of: [
            { type: "not", check: { type: "tool_called", tool: "cancel_order", count: { min: 1 } } },
            { type: "output", matcher: { contains: "30 days" } },
          ],
        }}
      />,
    );
    const nodes = screen.getAllByTestId("check-node");
    expect(nodes.map((n) => n.getAttribute("data-type"))).toEqual(["all", "not", "tool_called", "output"]);
    expect(screen.getByText("cancel_order called at least 1")).toBeInTheDocument();
    expect(screen.getByText('agent output (any) contains "30 days"')).toBeInTheDocument();
  });
  it("falls back to JSON for an unknown check type", () => {
    render(<CheckTree check={{ type: "telepathy", foo: 1 }} />);
    expect(screen.getByTestId("check-node")).toHaveAttribute("data-type", "unknown");
    expect(screen.getByText(/"telepathy"/)).toBeInTheDocument();
  });
});
