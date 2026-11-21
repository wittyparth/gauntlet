"use client";

import type { ColumnDef } from "@tanstack/react-table";
import type { ReactNode } from "react";

import { DataTable } from "@/components/shared/data-table";
import { JsonBlock } from "@/components/shared/json-block";
import type { AuditRow } from "@/lib/api/hooks/security";

const COLUMNS: ColumnDef<AuditRow, unknown>[] = [
  {
    accessorKey: "ts",
    header: "Time",
    cell: ({ row }) => <span className="font-mono text-xs whitespace-nowrap">{new Date(row.original.ts).toLocaleString()}</span>,
  },
  { accessorKey: "actor", header: "Actor", cell: ({ row }) => <span className="font-mono text-xs">{row.original.actor}</span> },
  { accessorKey: "action", header: "Action", cell: ({ row }) => <span className="font-mono text-xs font-medium">{row.original.action}</span> },
  {
    id: "subject",
    header: "Subject",
    cell: ({ row }) => (
      <span className="font-mono text-xs">
        {row.original.subject_type} <span className="text-muted-foreground">{row.original.subject_id}</span>
      </span>
    ),
  },
  {
    id: "detail",
    header: "Detail",
    cell: ({ row }) =>
      Object.keys(row.original.detail).length === 0 ? (
        <span className="text-muted-foreground text-xs">none</span>
      ) : (
        <JsonBlock value={row.original.detail} label="detail" defaultOpen={false} />
      ),
  },
  {
    id: "hash",
    header: "Hash",
    cell: ({ row }) => <span className="text-muted-foreground font-mono text-xs">{row.original.hash.slice(0, 10)}</span>,
  },
];

export function AuditTable({ rows, isLoading, emptyState }: { rows: AuditRow[]; isLoading?: boolean; emptyState: ReactNode }) {
  return <DataTable columns={COLUMNS} data={rows} getRowId={(r) => r.id} rowTestId="audit-row" isLoading={isLoading} emptyState={emptyState} />;
}
