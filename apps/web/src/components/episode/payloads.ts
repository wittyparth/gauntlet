import type { EpisodeEvent } from "@/lib/api/models";

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);

export function messageText(e: EpisodeEvent): string {
  return str(e.payload.text) ?? "";
}

export type ToolCall = { tool: string; args: unknown; via: string | null; callId: string | null };
export function toolCall(e: EpisodeEvent): ToolCall {
  return {
    tool: str(e.payload.tool) ?? "(unknown tool)",
    args: e.payload.args,
    via: str(e.payload.via),
    callId: str(e.payload.call_id),
  };
}

export type ToolResult = {
  ok: boolean;
  error: string | null;
  result: unknown;
  patch: Record<string, unknown>[];
  callId: string | null;
};
export function toolResult(e: EpisodeEvent): ToolResult {
  const p = e.payload;
  return {
    ok: p.ok === true,
    error: str(p.error),
    result: p.result,
    patch: Array.isArray(p.patch) ? p.patch.filter(isRecord) : [],
    callId: str(p.call_id),
  };
}

export type Fault = { kind: string; tool: string | null };
export function faultInfo(e: EpisodeEvent): Fault {
  const f = e.payload.fault;
  if (isRecord(f)) return { kind: str(f.kind) ?? "fault", tool: str(f.tool) ?? str(e.payload.tool) };
  return { kind: str(f) ?? "fault", tool: str(e.payload.tool) };
}

export function endedInfo(e: EpisodeEvent) {
  return {
    outcome: str(e.payload.outcome),
    termination: str(e.payload.termination),
    detail: str(e.payload.detail),
  };
}

export const isMessage = (e: EpisodeEvent) => e.kind === "user_message" || e.kind === "agent_message";

/** One-line muted summary for events without a dedicated body. */
export function summarize(e: EpisodeEvent): string {
  switch (e.kind) {
    case "episode_started":
      return "Episode started";
    case "episode_ended": {
      const { outcome, termination, detail } = endedInfo(e);
      return `Ended: ${outcome ?? "?"} (${termination ?? "?"})${detail ? ` , ${detail}` : ""}`;
    }
    case "check_result":
      return `Check ${str(e.payload.check_id) ?? ""}: ${e.payload.holds === true ? "holds" : "does not hold"}`;
    case "verdict":
      return `Verdict ${str(e.payload.criterion) ?? ""}: ${str(e.payload.result) ?? ""}`;
    case "sim_note":
      return "Simulator note";
    default:
      return e.kind.replace(/_/g, " ");
  }
}
