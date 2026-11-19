import { describe, expect, it } from "vitest";

import type { EpisodeEvent } from "@/lib/api/models";

import { buildDiff, compareValues } from "./diff-entries";

const result = (seq: number, patch: unknown[]): EpisodeEvent => ({
  kind: "tool_result",
  actor: "tool",
  seq,
  sim_time: "2026-01-01T09:00:00Z",
  wall_ms: 0,
  payload: { ok: true, patch },
  origin: null,
  cost: null,
});

describe("buildDiff (journal fallback)", () => {
  it("maps add, replace and remove ops to kinds with the causing seq", () => {
    const events = [
      result(3, [{ op: "add", collection: "refunds", id: "ref_1", value: { amount: 129 } }]),
      result(6, [
        { op: "replace", collection: "orders", id: "o_17", before: { status: "delivered" }, value: { status: "refunded" } },
      ]),
      result(9, [{ op: "remove", collection: "carts", id: "c_1", before: { n: 1 } }]),
    ];
    const v = buildDiff(null, events);
    expect(v.source).toBe("journal");
    expect(v.entries.map((e) => [e.collection, e.id, e.kind, e.seq])).toEqual([
      ["refunds", "ref_1", "added", 3],
      ["orders", "o_17", "changed", 6],
      ["carts", "c_1", "removed", 9],
    ]);
    expect(v.entries[0].record).toEqual({ amount: 129 });
    expect(v.entries[2].record).toEqual({ n: 1 });
  });

  it("reports nested path changes with dotted paths", () => {
    expect(
      compareValues({ address: { city: "Boise", zip: "1" }, n: 1 }, { address: { city: "Denver", zip: "1" }, n: 1 }),
    ).toEqual([{ path: "address.city", before: "Boise", after: "Denver" }]);
  });

  it("reports changed lists whole", () => {
    expect(compareValues({ coupons: ["A"] }, { coupons: ["A", "B"] })).toEqual([
      { path: "coupons", before: ["A"], after: ["A", "B"] },
    ]);
  });

  it("groups by collection and orders by seq", () => {
    const v = buildDiff(null, [
      result(2, [{ op: "add", collection: "b", id: "1", value: {} }]),
      result(5, [{ op: "add", collection: "a", id: "2", value: {} }]),
      result(7, [{ op: "add", collection: "b", id: "3", value: {} }]),
    ]);
    expect(v.groups.map((g) => [g.collection, g.entries.map((e) => e.seq), g.added])).toEqual([
      ["b", [2, 7], 2],
      ["a", [5], 1],
    ]);
  });
});

describe("buildDiff (server diff)", () => {
  it("uses the server diff when present", () => {
    const v = buildDiff(
      {
        changes: [
          {
            collection: "orders",
            id: "ord_6",
            kind: "changed",
            fields: [{ path: "status", old: "processing", new: "cancelled" }],
            record: null,
            seqs: [3],
          },
        ],
      },
      [],
    );
    expect(v.source).toBe("server");
    expect(v.entries).toEqual([
      {
        collection: "orders",
        id: "ord_6",
        kind: "changed",
        seq: 3,
        record: undefined,
        changes: [{ path: "status", before: "processing", after: "cancelled" }],
      },
    ]);
  });
});
