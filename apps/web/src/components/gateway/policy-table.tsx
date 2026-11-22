"use client";

import type { ColumnDef } from "@tanstack/react-table";

import { DataTable } from "@/components/shared/data-table";
import { Badge } from "@/components/ui/badge";
import type { PolicyOut } from "@/lib/api/hooks/policies";
import { timeAgo } from "@/lib/format";

const columns: ColumnDef<PolicyOut, unknown>[] = [
  { header: "Policy", cell: ({ row }) => <span>{row.original.name}</span> },
  { header: "Version", cell: ({ row }) => <span className="font-mono text-xs">v{row.original.version}</span> },
  {
    header: "Mode",
    cell: ({ row }) =>
      row.original.status === "draft" ? (
        <Badge variant="outline">draft</Badge>
      ) : row.original.policy.mode === "enforce" ? (
        <Badge variant="outline" className="border-destructive/40 text-destructive">enforce</Badge>
      ) : (
        <Badge variant="secondary">shadow</Badge>
      ),
  },
  { header: "Fail", cell: ({ row }) => <span className="text-xs">{row.original.policy.fail}</span> },
  { header: "Rules", cell: ({ row }) => <span className="font-mono text-xs">{row.original.policy.rules.length}</span> },
  { header: "Updated", cell: ({ row }) => <span className="text-muted-foreground text-xs">{timeAgo(row.original.created_at)}</span> },
];

export function PolicyTable({ policies, isLoading }: { policies: PolicyOut[]; isLoading?: boolean }) {
  return <DataTable columns={columns} data={policies} isLoading={isLoading} getRowId={(p) => p.id} rowHref={(p) => `/gateway/policies/${p.id}`} rowTestId="policy-row" />;
}
