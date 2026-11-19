"use client";

import type { ColumnDef } from "@tanstack/react-table";

import { DataTable } from "@/components/shared/data-table";
import { shortId, timeAgo } from "@/lib/format";
import type { Agent } from "@/lib/api/models";

const columns: ColumnDef<Agent, unknown>[] = [
  { header: "Name", cell: ({ row }) => <span className="font-medium">{row.original.name}</span> },
  {
    header: "Latest version",
    cell: ({ row }) => <span className="font-mono text-xs">{row.original.latest_version_id ? shortId(row.original.latest_version_id) : "none"}</span>,
  },
  { header: "Created", cell: ({ row }) => <span className="text-muted-foreground">{timeAgo(row.original.created_at)}</span> },
];

export function AgentTable({ agents, isLoading, emptyState }: { agents: Agent[]; isLoading?: boolean; emptyState: React.ReactNode }) {
  return (
    <DataTable
      columns={columns}
      data={agents}
      isLoading={isLoading}
      getRowId={(a) => a.id}
      rowTestId="agent-row"
      rowHref={(a) => `/agents/${a.id}`}
      emptyState={emptyState}
    />
  );
}
