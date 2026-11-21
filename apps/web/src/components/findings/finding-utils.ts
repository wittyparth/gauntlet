import type { Finding, FindingDetail } from "@/lib/api/hooks/findings";

/** Status values from the contract enum, in lifecycle order. */
export const STATUSES = [
  { value: "open", label: "Open" },
  { value: "triaged", label: "Triaged" },
  { value: "in_progress", label: "In progress" },
  { value: "fixed", label: "Fixed" },
  { value: "verified", label: "Verified" },
  { value: "accepted_risk", label: "Accepted risk" },
  { value: "false_positive", label: "False positive" },
] as const;

export const statusLabel = (status: string) =>
  STATUSES.find((s) => s.value === status)?.label ?? status.replace(/_/g, " ");

const SEVERITY_RANK: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
export const severityRank = (s: string) => SEVERITY_RANK[s] ?? 4;

/** Default inbox order: severity, then newest first. */
export function sortFindings<T extends Pick<Finding, "severity" | "created_at">>(rows: T[]): T[] {
  return [...rows].sort(
    (a, b) => severityRank(a.severity) - severityRank(b.severity) || b.created_at.localeCompare(a.created_at),
  );
}

export const reproText = (r: readonly number[]) => `${r[0]}/${r[1]}`;
export const reproSentence = (r: readonly number[]) => `${r[0]} of ${r[1]} reproduced`;

/** Attack text of a reproducer: the scripted user turns when the attack is a user turn. */
export function attackPayload(reproducer: FindingDetail["reproducer"]): string | null {
  const turns = reproducer.tags?.attack_turns;
  if (turns) {
    try {
      const parsed: unknown = JSON.parse(turns);
      if (Array.isArray(parsed)) return parsed.map(String).join("\n\n");
    } catch {
      return turns;
    }
  }
  return reproducer.opening_message ?? null;
}

/** The objective check of a placed reproducer (forbidden entry `objective`). */
export function objectiveCheck(reproducer: FindingDetail["reproducer"]): unknown {
  return reproducer.forbidden.find((f) => f.id === "objective")?.check ?? null;
}

/** Host of a target URL, or null when the target is not remote. */
export function targetHost(target: { kind: string; base_url?: string; url?: string }): string | null {
  const raw = target.kind === "openai_compat" ? target.base_url : target.kind === "http" ? target.url : undefined;
  if (!raw) return null;
  try {
    return new URL(raw).hostname.toLowerCase();
  } catch {
    return null;
  }
}

/** A verification covers its host and any subdomain of it. */
export function hostCovered(host: string, verifiedHosts: string[]): boolean {
  return verifiedHosts.some((v) => host === v || host.endsWith(`.${v}`));
}

const LOOPBACK = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);
export const isLoopback = (host: string) => LOOPBACK.has(host);

/** 0 for no data, 1 to 5 for rate bands of an attack success rate. */
export function heatStep(attempts: number, successes: number): 0 | 1 | 2 | 3 | 4 | 5 {
  if (attempts <= 0) return 0;
  const r = successes / attempts;
  if (r === 0) return 1;
  if (r <= 0.25) return 2;
  if (r <= 0.5) return 3;
  if (r <= 0.75) return 4;
  return 5;
}
