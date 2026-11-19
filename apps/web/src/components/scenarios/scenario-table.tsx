"use client";

import type { ColumnDef } from "@tanstack/react-table";

import { ShieldCheck } from "@/components/animate-ui/icons/shield-check";
import { DataTable } from "@/components/shared/data-table";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { ScenarioRecord } from "@/lib/api/models";

function Tags({ tags }: { tags: Record<string, string> }) {
  const all = Object.entries(tags).map(([k, v]) => `${k}:${v}`);
  const shown = all.slice(0, 3);
  const rest = all.slice(3);
  return (
    <div className="flex flex-nowrap items-center gap-1 whitespace-nowrap">
      {shown.map((t) => (
        <Badge key={t} variant="outline" className="font-mono">{t}</Badge>
      ))}
      {rest.length > 0 ? (
        <Tooltip>
          <TooltipTrigger render={<Badge variant="secondary" />}>+{rest.length}</TooltipTrigger>
          <TooltipContent>{rest.join(", ")}</TooltipContent>
        </Tooltip>
      ) : null}
    </div>
  );
}

const columns: ColumnDef<ScenarioRecord, unknown>[] = [
  { header: "Title", cell: ({ row }) => <span className="font-medium">{row.original.scenario.title}</span> },
  { header: "Persona", cell: ({ row }) => <span className="font-mono text-xs">{row.original.scenario.persona}</span> },
  { header: "Tags", cell: ({ row }) => <Tags tags={row.original.scenario.tags} /> },
  { header: "Source", cell: ({ row }) => <span>{row.original.source}</span> },
  {
    header: "Status",
    cell: ({ row }) => (
      <Badge variant={row.original.status === "approved" ? "secondary" : "outline"}>
        {row.original.status === "draft" ? "Draft" : row.original.status === "approved" ? "Approved" : row.original.status}
      </Badge>
    ),
  },
  { header: "v", cell: ({ row }) => <span className="font-mono text-xs">{row.original.version}</span> },
  {
    header: "Security",
    cell: ({ row }) =>
      row.original.scenario.attack ? (
        <span className="text-info inline-flex items-center gap-1" title="Security scenario">
          <ShieldCheck size={14} /> <span className="sr-only">Security scenario</span>
        </span>
      ) : null,
  },
];

export function ScenarioTable({ rows, isLoading, emptyState }: { rows: ScenarioRecord[]; isLoading?: boolean; emptyState: React.ReactNode }) {
  return (
    <DataTable
      columns={columns}
      data={rows}
      isLoading={isLoading}
      getRowId={(r) => r.id}
      rowTestId="scenario-row"
      rowHref={(r) => `/scenarios/${r.id}`}
      emptyState={emptyState}
    />
  );
}
