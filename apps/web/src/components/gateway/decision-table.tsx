"use client";

import type { ColumnDef } from "@tanstack/react-table";

import { DataTable } from "@/components/shared/data-table";
import { Badge } from "@/components/ui/badge";
import type { Decision } from "@/lib/api/hooks/gateway";

const TONE: Record<string, string> = {
  block: "border-destructive/40 text-destructive",
  require_approval: "border-warning/40 text-warning",
  redact: "border-info/40 text-info",
  log: "text-muted-foreground",
  allow: "text-muted-foreground",
};

export function ActionBadge({ action }: { action: string }) {
  return <Badge variant="outline" className={TONE[action]}>{action.replace("_", " ")}</Badge>;
}

const columns: ColumnDef<Decision, unknown>[] = [
  { header: "Time", cell: ({ row }) => <span className="font-mono text-xs">{new Date(row.original.ts).toLocaleTimeString()}</span> },
  {
    header: "Action",
    cell: ({ row }) => (
      <span className="flex items-center gap-1">
        <ActionBadge action={row.original.action} />
        {!row.original.enforced && row.original.would_have && row.original.would_have !== "allow" ? <Badge variant="secondary">shadow, would {row.original.would_have.replace("_", " ")}</Badge> : null}
      </span>
    ),
  },
  { header: "Rule", cell: ({ row }) => <span className="font-mono text-xs">{row.original.rule_id ?? "-"}</span> },
  { header: "Tool / message", cell: ({ row }) => <span className="font-mono text-xs">{row.original.tool ?? row.original.kind}</span> },
  { header: "Agent", cell: ({ row }) => <span className="text-muted-foreground font-mono text-xs">{row.original.agent_id ?? "-"}</span> },
];

export function DecisionTable({ decisions, isLoading, onOpen }: { decisions: Decision[]; isLoading?: boolean; onOpen: (d: Decision) => void }) {
  return (
    <DataTable
      columns={columns}
      data={decisions}
      isLoading={isLoading}
      getRowId={(d) => d.id}
      onRowClick={onOpen}
      onRowOpen={onOpen}
      rowTestId="decision-row"
      rowClassName={() => "animate-in fade-in duration-300"}
    />
  );
}
