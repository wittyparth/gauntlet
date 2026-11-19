"use client";

import type { ColumnDef } from "@tanstack/react-table";

import { RiskBadge } from "@/components/shared/badges";
import { DataTable } from "@/components/shared/data-table";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingRows } from "@/components/shared/loading";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { useWorld } from "@/lib/api/hooks/read";
import type { ToolSpec } from "@/lib/api/models";

const RISK_ORDER = ["financial", "destructive", "external_comm", "write", "read"];
const rank = (r: string) => {
  const i = RISK_ORDER.indexOf(r);
  return i < 0 ? 99 : i;
};

const columns: ColumnDef<ToolSpec, unknown>[] = [
  {
    header: "Tool",
    cell: ({ row }) => (
      <HoverCard>
        <HoverCardTrigger render={<span className="font-mono text-xs" />}>{row.original.name}</HoverCardTrigger>
        <HoverCardContent className="w-72 text-xs">{row.original.description || "No description."}</HoverCardContent>
      </HoverCard>
    ),
  },
  { header: "Risk", cell: ({ row }) => <RiskBadge risk={row.original.risk} /> },
  { header: "Handler", cell: ({ row }) => <span className="font-mono text-xs">{row.original.handler.kind}</span> },
  {
    header: "Flags",
    cell: ({ row }) => (
      <div className="flex gap-1">
        {row.original.untrusted_output ? <Badge variant="outline">untrusted output</Badge> : null}
        {row.original.honeytool ? <Badge variant="outline">honeytool</Badge> : null}
      </div>
    ),
  },
];

export function ToolInventory({ worldId, allowed }: { worldId: string | null | undefined; allowed: string[] | null | undefined }) {
  const w = useWorld(worldId);
  const tools = (w.data?.tools ?? [])
    .filter((t) => !allowed || allowed.includes(t.name))
    .sort((a, b) => rank(a.risk) - rank(b.risk) || a.name.localeCompare(b.name));
  return (
    <Card size="sm">
      <CardHeader><CardTitle><h2 className="text-sm font-medium">Tools{w.data ? ` (${tools.length})` : ""}</h2></CardTitle></CardHeader>
      <CardContent>
        {!worldId ? (
          <EmptyState title="No world linked" body="This version was created without a world, so there is no tool list to show." />
        ) : w.isLoading ? (
          <LoadingRows rows={5} />
        ) : w.error ? (
          <ErrorState error={w.error} onRetry={() => w.refetch()} />
        ) : (
          <DataTable columns={columns} data={tools} getRowId={(t) => t.name} rowTestId="tool-row" emptyState={<EmptyState title="No tools" body="This agent has no tools enabled in this world." />} />
        )}
      </CardContent>
    </Card>
  );
}
