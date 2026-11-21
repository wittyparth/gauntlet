"use client";

import type { ColumnDef } from "@tanstack/react-table";
import { useMemo, type ReactNode } from "react";

import { SeverityBadge } from "@/components/shared/badges";
import { DataTable } from "@/components/shared/data-table";
import type { Finding } from "@/lib/api/hooks/findings";
import { timeAgo } from "@/lib/format";

import { reproText, severityRank, sortFindings } from "./finding-utils";
import { FindingStatusBadge } from "./status-badge";

export function FindingTable({
  findings,
  versionLabels,
  isLoading,
  emptyState,
}: {
  findings: Finding[];
  versionLabels: Map<string, string>;
  isLoading?: boolean;
  emptyState: ReactNode;
}) {
  const columns = useMemo<ColumnDef<Finding, unknown>[]>(
    () => [
      {
        id: "severity",
        header: "Severity",
        sortingFn: (a, b) => severityRank(a.original.severity) - severityRank(b.original.severity),
        cell: ({ row }) => <SeverityBadge severity={row.original.severity} />,
      },
      {
        accessorKey: "title",
        header: "Title",
        cell: ({ row }) => <span className="block max-w-[34ch] truncate font-medium">{row.original.title}</span>,
      },
      {
        accessorKey: "category",
        header: "Category",
        cell: ({ row }) => <span className="font-mono text-xs">{row.original.category}</span>,
      },
      {
        id: "repro",
        header: "Repro",
        cell: ({ row }) => <span className="font-mono text-xs tabular-nums">{reproText(row.original.reproducibility)}</span>,
      },
      {
        id: "agent",
        header: "Agent version",
        cell: ({ row }) => (
          <span className="text-muted-foreground text-xs">
            {versionLabels.get(row.original.agent_version_id) ?? row.original.agent_version_id}
          </span>
        ),
      },
      { id: "status", header: "Status", cell: ({ row }) => <FindingStatusBadge status={row.original.status} /> },
      {
        accessorKey: "updated_at",
        header: "Updated",
        cell: ({ row }) => <span className="text-muted-foreground text-xs">{timeAgo(row.original.updated_at)}</span>,
      },
    ],
    [versionLabels],
  );
  return (
    <DataTable
      columns={columns}
      data={sortFindings(findings)}
      getRowId={(f) => f.id}
      rowHref={(f) => `/findings/${f.id}`}
      rowTestId="finding-row"
      isLoading={isLoading}
      emptyState={emptyState}
    />
  );
}
