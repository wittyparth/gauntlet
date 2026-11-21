"use client";

import type { ColumnDef } from "@tanstack/react-table";

import { SeverityBadge } from "@/components/shared/badges";
import { DataTable } from "@/components/shared/data-table";
import { Badge } from "@/components/ui/badge";
import type { RubricDoc } from "@/lib/api/hooks/rubrics";

const columns: ColumnDef<RubricDoc, unknown>[] = [
  { header: "Rubric", cell: ({ row }) => <span>{row.original.title}</span> },
  { header: "Version", cell: ({ row }) => <span className="font-mono text-xs">v{row.original.version}</span> },
  { header: "Severity", cell: ({ row }) => <SeverityBadge severity={row.original.severity} /> },
  { header: "Hard fail", cell: ({ row }) => (row.original.hard_fail ? <Badge variant="outline">hard fail</Badge> : <span className="text-muted-foreground">-</span>) },
  {
    header: "Calibration",
    cell: ({ row }) =>
      row.original.gating_allowed ? (
        <Badge variant="outline" className="border-success/40 text-success">gating allowed</Badge>
      ) : (
        <Badge variant="outline">not calibrated</Badge>
      ),
  },
];

export function RubricTable({ rubrics, isLoading }: { rubrics: RubricDoc[]; isLoading?: boolean }) {
  return (
    <DataTable
      columns={columns}
      data={rubrics}
      isLoading={isLoading}
      getRowId={(r) => r.id}
      rowHref={(r) => `/rubrics/${r.id}`}
      rowTestId="rubric-row"
    />
  );
}
