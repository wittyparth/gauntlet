"use client";

import type { ColumnDef } from "@tanstack/react-table";
import Link from "next/link";

import { DataTable } from "@/components/shared/data-table";
import { EmptyState } from "@/components/shared/empty-state";
import { LiveStatusText } from "@/components/shared/live-status-text";
import { StatCard } from "@/components/shared/stat-card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { reportOf, type PolicyTest, type PolicyTestReport } from "@/lib/api/hooks/policies";
import { formatPercent } from "@/lib/format";

import { RuleBreakdownTable } from "./rule-breakdown-table";
import { TradeoffChart } from "./tradeoff-chart";

type Outcome = PolicyTestReport["outcomes"][number];
const columns: ColumnDef<Outcome, unknown>[] = [
  {
    header: "Episode",
    cell: ({ row }) => {
      const o = row.original;
      const href = `/episodes/${o.episode_id}${o.first_block_seq != null ? `#e-${o.first_block_seq}` : ""}`;
      return <Link href={href} className="font-mono text-xs underline" onClick={(e) => e.stopPropagation()}>{o.episode_id}</Link>;
    },
  },
  { header: "Kind", cell: ({ row }) => <Badge variant="secondary">{row.original.kind}</Badge> },
  { header: "First block", cell: ({ row }) => <span className="font-mono text-xs">{row.original.first_block_seq != null ? `[${row.original.first_block_seq}] ${row.original.rule_id ?? ""}` : "never"}</span> },
  { header: "Result", cell: ({ row }) => <span className="text-xs">{row.original.kind === "attack" ? (row.original.effective ? "blocked in time" : "not stopped") : row.original.effective ? "broken by a block" : "unaffected"}</span> },
];

export function PolicyTestResults({ test, running }: { test: PolicyTest | undefined; running: boolean }) {
  if (running || test?.status === "queued" || test?.status === "running") {
    return (
      <div className="flex flex-col gap-2" data-testid="test-running">
        <LiveStatusText text="Running the policy test" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (!test) return <EmptyState title="Not tested yet" body="Run a test to replay stored attack and benign trajectories against this version, without any model calls." />;
  if (test.status === "failed" || test.error) return <EmptyState title="The last test failed" body={test.error ?? "No details were stored."} />;
  const r = reportOf(test);
  if (!r) return null;
  if (r.attacks === 0 && r.benign === 0) {
    return <EmptyState title="Nothing to replay" body="No stored attack or benign trajectories for this agent version. Run a campaign and a normal suite first." />;
  }
  return (
    <div className="flex flex-col gap-4" data-testid="test-results">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard name="block-rate" label="Block rate" value={formatPercent(r.block_rate)} hint={`${r.blocked} of ${r.attacks} attacks stopped in time`} />
        <StatCard name="fp-rate" label="False-positive rate" value={formatPercent(r.fp_rate)} hint={`${r.broken} of ${r.benign} benign trajectories broken`} />
        <StatCard name="attacks" label="Attack trajectories" value={r.attacks} />
        <StatCard name="benign" label="Benign trajectories" value={<span>{r.benign}{r.skipped ? <span className="text-muted-foreground text-sm"> ({r.skipped} skipped)</span> : null}</span>} />
      </div>
      <TradeoffChart rows={r.tradeoff} />
      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">Per rule</h3>
        <RuleBreakdownTable rows={r.per_rule} />
      </div>
      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">Trajectories</h3>
        <DataTable columns={columns} data={r.outcomes} getRowId={(o) => o.episode_id} rowTestId="outcome-row" />
      </div>
    </div>
  );
}
