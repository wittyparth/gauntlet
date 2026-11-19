"use client";

import type { ColumnDef } from "@tanstack/react-table";

import { RunStatusBadge } from "@/components/shared/badges";
import { DataTable } from "@/components/shared/data-table";
import { Money } from "@/components/shared/live-number";
import type { Run } from "@/lib/api/models";
import { isTerminalRun } from "@/lib/api/models";
import { shortId, timeAgo } from "@/lib/format";

const columns: ColumnDef<Run, unknown>[] = [
  { header: "Status", cell: ({ row }) => <RunStatusBadge status={row.original.status} /> },
  { header: "Suite", cell: ({ row }) => <span className="font-mono text-xs">{row.original.suite_id}</span> },
  {
    header: "Agent version",
    cell: ({ row }) => <span>{row.original.manifest?.agent_version?.label ?? shortId(row.original.agent_version_id)}</span>,
  },
  {
    header: "Episodes",
    cell: ({ row }) => (
      <span className="font-mono text-xs">
        {row.original.counts.done}/{row.original.counts.total}
      </span>
    ),
  },
  { header: "Cost", cell: ({ row }) => <Money usdMicros={row.original.spent_usd_micros} /> },
  { header: "Created", cell: ({ row }) => <span className="text-muted-foreground">{timeAgo(row.original.created_at)}</span> },
];

export function RunTable({ runs, isLoading, emptyState }: { runs: Run[]; isLoading?: boolean; emptyState: React.ReactNode }) {
  return (
    <DataTable
      columns={columns}
      data={runs}
      isLoading={isLoading}
      getRowId={(r) => r.id}
      rowTestId="run-row"
      rowHref={(r) => (isTerminalRun(r.status) ? `/runs/${r.id}/report` : `/runs/${r.id}`)}
      emptyState={emptyState}
    />
  );
}
