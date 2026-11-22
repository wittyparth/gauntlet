import { describeCheck } from "@/components/scenarios/describe-check";

export type CheckParse = { ok: true; value: unknown } | { ok: false; message: string; position: number | null };

/** The unknown `type` nearest the root, as a path like `when.args[1]`; null when every node is known. */
function unknownNode(check: unknown, path: string): string | null {
  const d = describeCheck(check);
  if (!d.known) return path;
  for (let i = 0; i < d.children.length; i++) {
    const hit = unknownNode(d.children[i], `${path}[${i}]`);
    if (hit) return hit;
  }
  return null;
}

/**
 * Client-side check of the `when` JSON: syntax first (with the character position when the engine
 * reports it), then every node must have a known `type`. The server stays the authority: it also
 * rejects checks that cannot be evaluated on a prefix (`judge`, `state_diff`).
 */
export function parseCheck(text: string): CheckParse {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch (e) {
    const message = e instanceof Error ? e.message : "Invalid JSON";
    const m = /position (\d+)/.exec(message);
    return { ok: false, message: `Not valid JSON: ${message}`, position: m ? Number(m[1]) : null };
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return { ok: false, message: "A check is a JSON object with a \"type\".", position: null };
  }
  const bad = unknownNode(value, "when");
  if (bad) {
    const t = (value as { type?: unknown }).type;
    return { ok: false, message: `Unknown check type at ${bad}${bad === "when" && typeof t === "string" ? `: "${t}"` : ""}.`, position: null };
  }
  return { ok: true, value };
}
