import type { PolicyTestReport } from "@/lib/api/hooks/policies";

export type Mode = "shadow" | "enforce";
export type FailMode = "open" | "closed";

/** Which changes need the confirmation dialog: shadow to enforce, and open to closed. */
export function needsConfirm(cur: { mode: Mode; fail: FailMode }, next: { mode: Mode; fail: FailMode }): boolean {
  return (cur.mode === "shadow" && next.mode === "enforce") || (cur.fail === "open" && next.fail === "closed");
}

/** What the dialog shows: the latest test numbers, or the warning that the version is untested. */
export function confirmSummary(report: PolicyTestReport | null): { tested: false; text: string } | { tested: true; text: string; blockRate: number; fpRate: number } {
  if (!report) return { tested: false, text: "This version has not been tested." };
  return {
    tested: true,
    blockRate: report.block_rate,
    fpRate: report.fp_rate,
    text: `Last test: block rate ${Math.round(report.block_rate * 100)}%, false-positive rate ${Math.round(report.fp_rate * 100)}%.`,
  };
}
