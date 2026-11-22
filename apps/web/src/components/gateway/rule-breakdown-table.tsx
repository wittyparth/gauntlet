"use client";

import type { ColumnDef } from "@tanstack/react-table";

import { DataTable } from "@/components/shared/data-table";
import type { PolicyTestReport } from "@/lib/api/hooks/policies";

type Row = PolicyTestReport["per_rule"][number];
const columns: ColumnDef<Row, unknown>[] = [
  { header: "Rule", cell: ({ row }) => <span className="font-mono text-xs">{row.original.rule_id}</span> },
  { header: "Attacks it stops alone", cell: ({ row }) => <span className="font-mono text-xs">{row.original.blocked}</span> },
  { header: "Benign it breaks alone", cell: ({ row }) => <span className="font-mono text-xs">{row.original.false_positives}</span> },
];

export function RuleBreakdownTable({ rows }: { rows: Row[] }) {
  return <DataTable columns={columns} data={rows} getRowId={(r) => r.rule_id} rowTestId="breakdown-row" />;
}
