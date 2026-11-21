"use client";

import type { ColumnDef } from "@tanstack/react-table";

import { DataTable } from "@/components/shared/data-table";
import { Badge } from "@/components/ui/badge";
import type { ParetoPoint } from "@/lib/api/hooks/migration";
import { formatPercent, formatUsd } from "@/lib/format";

const columns: ColumnDef<ParetoPoint, unknown>[] = [
  { header: "Version", cell: ({ row }) => <span>{row.original.label}{row.original.model ? <span className="text-muted-foreground ml-2 font-mono text-xs">{row.original.model}</span> : null}</span> },
  {
    header: "Pass rate",
    cell: ({ row }) => {
      const p = row.original;
      return <span className="font-mono text-xs">{p.pass_rate != null ? formatPercent(p.pass_rate) : "n/a"}{p.ci_low != null && p.ci_high != null ? ` (${formatPercent(p.ci_low)} to ${formatPercent(p.ci_high)})` : ""}</span>;
    },
  },
  { header: "Cost per episode", cell: ({ row }) => <span className="font-mono text-xs">{formatUsd(row.original.cost_per_episode_usd_micros)}</span> },
  { header: "Latency p95", cell: ({ row }) => <span className="font-mono text-xs">{row.original.latency_p95_ms != null ? `${row.original.latency_p95_ms} ms` : "n/a"}</span> },
  { header: "Frontier", cell: ({ row }) => (row.original.on_frontier ? <Badge variant="outline" className="border-success/40 text-success">on frontier</Badge> : <Badge variant="outline">dominated</Badge>) },
];

export function MigrationTable({ points }: { points: ParetoPoint[] }) {
  return <DataTable columns={columns} data={points} getRowId={(p) => p.run_id} rowTestId="pareto-row" />;
}
