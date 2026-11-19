"use client";

import type { ColumnDef } from "@tanstack/react-table";

import { EpisodeStatusBadge, OutcomeBadge, countsTowardStats } from "@/components/shared/badges";
import { DataTable } from "@/components/shared/data-table";
import { Money } from "@/components/shared/live-number";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { EpisodeRow } from "@/lib/api/models";

export function EpisodeTable({
  episodes,
  titles,
  selectedId,
  onSelect,
  onOpen,
  isLoading,
  emptyState,
  live,
}: {
  episodes: EpisodeRow[];
  titles: Map<string, string>;
  selectedId: string | null;
  onSelect: (e: EpisodeRow) => void;
  onOpen: (e: EpisodeRow) => void;
  isLoading?: boolean;
  emptyState: React.ReactNode;
  live?: boolean;
}) {
  const columns: ColumnDef<EpisodeRow, unknown>[] = [
    {
      header: "Scenario",
      cell: ({ row }) => <span>{titles.get(row.original.scenario_id) ?? row.original.scenario_id}</span>,
    },
    { header: "Rep", cell: ({ row }) => <span className="font-mono text-xs">{row.original.rep + 1}</span> },
    { header: "Status", cell: ({ row }) => <EpisodeStatusBadge status={row.original.status} /> },
    {
      header: "Outcome",
      cell: ({ row }) =>
        row.original.outcome ? (
          countsTowardStats(row.original.outcome) ? (
            <OutcomeBadge outcome={row.original.outcome} />
          ) : (
            <Tooltip>
              <TooltipTrigger render={<span />}>
                <OutcomeBadge outcome={row.original.outcome} />
              </TooltipTrigger>
              <TooltipContent>Excluded from pass rate</TooltipContent>
            </Tooltip>
          )
        ) : (
          <span className="text-muted-foreground">-</span>
        ),
    },
    { header: "Cost", cell: ({ row }) => <Money usdMicros={row.original.cost_usd_micros} live={live && row.original.status === "leased"} /> },
  ];
  return (
    <DataTable
      columns={columns}
      data={episodes}
      isLoading={isLoading}
      getRowId={(e) => e.id}
      rowTestId="episode-row"
      selectedId={selectedId}
      onRowClick={onSelect}
      onRowOpen={onOpen}
      emptyState={emptyState}
    />
  );
}
