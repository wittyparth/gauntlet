"use client";

import type { ColumnDef } from "@tanstack/react-table";

import { RiskBadge } from "@/components/shared/badges";
import { DataTable } from "@/components/shared/data-table";
import { Badge } from "@/components/ui/badge";
import type { Posture } from "@/lib/api/hooks/security";

type Row = Posture["tool_review"][number];

const COLUMNS: ColumnDef<Row, unknown>[] = [
  { accessorKey: "tool", header: "Tool", cell: ({ row }) => <span className="font-mono text-xs">{row.original.tool}</span> },
  { id: "risk", header: "Risk", cell: ({ row }) => <RiskBadge risk={row.original.risk} /> },
  { accessorKey: "calls", header: "Calls", cell: ({ row }) => <span className="font-mono text-xs tabular-nums">{row.original.calls}</span> },
  {
    accessorKey: "tainted_calls",
    header: "Tainted calls",
    cell: ({ row }) => <span className="font-mono text-xs tabular-nums">{row.original.tainted_calls}</span>,
  },
  {
    accessorKey: "honeytool_calls",
    header: "Honeytool calls",
    cell: ({ row }) => <span className="font-mono text-xs tabular-nums">{row.original.honeytool_calls}</span>,
  },
  {
    id: "privilege",
    header: "Privilege",
    cell: ({ row }) =>
      row.original.over_privileged ? (
        <span className="flex flex-col gap-0.5">
          <Badge variant="outline" className="border-warning/40 text-warning w-fit">
            Over-privileged
          </Badge>
          <span className="text-muted-foreground text-xs">{row.original.reasons.join("; ")}</span>
        </span>
      ) : (
        <span className="text-muted-foreground text-xs">Within need</span>
      ),
  },
];

export function ToolPermissionTable({ tools }: { tools: Row[] }) {
  return <DataTable columns={COLUMNS} data={tools} getRowId={(t) => t.tool} rowTestId="tool-row" />;
}
