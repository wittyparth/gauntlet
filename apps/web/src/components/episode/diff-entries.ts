import type { DiffChange, EpisodeEvent } from "@/lib/api/models";

import { toolResult } from "./payloads";

export type DiffKind = "added" | "removed" | "changed";
export type FieldChange = { path: string; before: unknown; after: unknown };
export type DiffEntry = {
  collection: string;
  id: string;
  kind: DiffKind;
  seq: number;
  record?: unknown;
  changes?: FieldChange[];
};
export type DiffGroup = { collection: string; entries: DiffEntry[]; added: number; removed: number; changed: number };
export type DiffView = { source: "server" | "journal"; entries: DiffEntry[]; groups: DiffGroup[] };

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

/** Dotted-path differences; lists are compared and reported whole. */
export function compareValues(before: unknown, after: unknown, path = ""): FieldChange[] {
  if (isRecord(before) && isRecord(after)) {
    const out: FieldChange[] = [];
    for (const key of new Set([...Object.keys(before), ...Object.keys(after)])) {
      out.push(...compareValues(before[key], after[key], path ? `${path}.${key}` : key));
    }
    return out;
  }
  if (JSON.stringify(before) === JSON.stringify(after)) return [];
  return [{ path: path || "(value)", before, after }];
}

function fromServer(changes: DiffChange[]): DiffEntry[] {
  return changes.map((c) => ({
    collection: c.collection,
    id: c.id,
    kind: c.kind,
    seq: c.seqs[0] ?? -1,
    record: c.record ?? undefined,
    changes: c.kind === "changed" ? c.fields.map((f) => ({ path: f.path, before: f.old, after: f.new })) : undefined,
  }));
}

function fromJournal(events: EpisodeEvent[]): DiffEntry[] {
  const out: DiffEntry[] = [];
  for (const e of events) {
    if (e.kind !== "tool_result") continue;
    for (const op of toolResult(e).patch) {
      const collection = String(op.collection ?? "");
      const id = String(op.id ?? "");
      if (op.op === "add") out.push({ collection, id, kind: "added", seq: e.seq, record: op.value });
      else if (op.op === "remove") out.push({ collection, id, kind: "removed", seq: e.seq, record: op.before });
      else if (op.op === "replace")
        out.push({ collection, id, kind: "changed", seq: e.seq, changes: compareValues(op.before, op.value) });
    }
  }
  return out;
}

function group(entries: DiffEntry[]): DiffGroup[] {
  const by = new Map<string, DiffGroup>();
  for (const e of [...entries].sort((a, b) => a.seq - b.seq)) {
    const g = by.get(e.collection) ?? { collection: e.collection, entries: [], added: 0, removed: 0, changed: 0 };
    g.entries.push(e);
    g[e.kind] += 1;
    by.set(e.collection, g);
  }
  return [...by.values()];
}

/** Prefer the server-computed diff (compacted, with causing seqs); else build it from the journal. */
export function buildDiff(serverDiff: { changes: DiffChange[] } | null | undefined, events: EpisodeEvent[]): DiffView {
  const source = serverDiff ? "server" : "journal";
  const entries = serverDiff ? fromServer(serverDiff.changes) : fromJournal(events);
  return { source, entries, groups: group(entries) };
}
