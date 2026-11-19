/** Turns a `Check` (contracts section 4) into a label, a one-line summary and child checks. */
export type Described = {
  type: string;
  summary: string;
  children: unknown[];
  known: boolean;
};

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

const OPS = ["eq", "ne", "in", "regex", "contains", "gt", "gte", "lt", "lte", "exists"] as const;

export function describeMatcher(m: unknown): string {
  if (!isRecord(m)) return String(m);
  const parts: string[] = [];
  for (const op of OPS) {
    if (m[op] === undefined || m[op] === null) continue;
    const v = m[op];
    parts.push(op === "regex" ? `matches /${String(v)}/` : `${op} ${JSON.stringify(v)}`);
  }
  if (typeof m.ref === "string") parts.push(`${m.ref_op ?? "eq"} ${m.ref}`);
  return parts.join(" and ") || "(any)";
}

function describeRange(r: unknown): string {
  if (!isRecord(r)) return "";
  const { min, max } = r as { min?: number | null; max?: number | null };
  if (min != null && max != null) return min === max ? `exactly ${min}` : `${min} to ${max}`;
  if (min != null) return `at least ${min}`;
  if (max != null) return `at most ${max}`;
  return "any number of times";
}

function describeArgs(args: unknown): string {
  if (!isRecord(args) || Object.keys(args).length === 0) return "";
  return ` with ${Object.entries(args)
    .map(([k, m]) => `${k} ${describeMatcher(m)}`)
    .join(", ")}`;
}

export function describeCheck(c: unknown): Described {
  if (!isRecord(c) || typeof c.type !== "string")
    return { type: "unknown", summary: "", children: [], known: false };
  const type = c.type;
  const leaf = (summary: string): Described => ({ type, summary, children: [], known: true });
  switch (type) {
    case "all":
    case "any":
      return {
        type,
        summary: type === "all" ? "every one must hold" : "at least one must hold",
        children: Array.isArray(c.of) ? c.of : [],
        known: true,
      };
    case "not":
      return { type, summary: "must not hold", children: c.check === undefined ? [] : [c.check], known: true };
    case "sequence":
      return { type, summary: `${c.strict ? "immediately " : ""}first, then`, children: [c.first, c.then], known: true };
    case "tool_called":
      return leaf(
        `${String(c.tool)} called ${describeRange(c.count)}${describeArgs(c.args)}${
          c.ok === true ? " (succeeded)" : c.ok === false ? " (failed)" : ""
        }`,
      );
    case "state": {
      const sel = c.id != null ? String(c.id) : `where ${JSON.stringify(c.where)}`;
      return leaf(`${String(c.collection)}:${sel} ${String(c.path)} ${describeMatcher(c.matcher)}`);
    }
    case "state_diff": {
      const bits = [
        c.added ? `added ${describeRange(c.added)}` : "",
        c.removed ? `removed ${describeRange(c.removed)}` : "",
        c.changed ? `changed ${Object.keys(c.changed as object).join(", ")}` : "",
        c.only ? "only these" : "",
      ].filter(Boolean);
      return leaf(`${String(c.collection)}: ${bits.join(", ") || "any change"}`);
    }
    case "output":
      return leaf(`agent output (${String(c.scope ?? "any")}) ${describeMatcher(c.matcher)}`);
    case "canary_leaked":
      return leaf(`canary ${String(c.canary ?? "*")} leaked`);
    case "egress":
      return leaf("data leaves to a domain or recipient outside the allow list");
    case "tainted_call":
      return leaf(`untrusted content reaches ${String(c.tool ?? "*")}`);
    case "detector":
      return leaf(`detector ${String(c.name)}`);
    case "judge":
      return leaf(`rubric ${String(c.rubric)}`);
    default:
      return { type, summary: "", children: [], known: false };
  }
}
