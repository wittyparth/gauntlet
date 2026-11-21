"use client";

import type { ColumnDef } from "@tanstack/react-table";
import Link from "next/link";
import { useState } from "react";

import { DataTable } from "@/components/shared/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { Report } from "@/lib/api/models";
import { formatPercent } from "@/lib/format";

type Row = Report["per_scenario"][number];

const columns = (runId: string, failing: Map<string, string[]>): ColumnDef<Row, unknown>[] => [
  {
    header: "Scenario",
    cell: ({ row }) => (
      <span className="flex flex-wrap items-center gap-2">
        {row.original.title}
        {row.original.flaky ? <Badge variant="outline" className="border-warning/40 text-warning">flaky</Badge> : null}
        {row.original.quarantined ? <Badge variant="secondary">quarantined</Badge> : null}
      </span>
    ),
  },
  { header: "Trials", cell: ({ row }) => <span className="font-mono text-xs">{row.original.counted}</span> },
  {
    header: "Pass rate",
    cell: ({ row }) => {
      const r = row.original;
      return (
        <div className="flex items-center gap-2">
          <Progress value={(r.rate ?? 0) * 100} className="w-24" aria-label="Pass rate" />
          <span className="font-mono text-xs">
            {r.rate != null ? formatPercent(r.rate) : "n/a"}
            {r.ci_low != null && r.ci_high != null ? ` (${formatPercent(r.ci_low)} to ${formatPercent(r.ci_high)})` : ""}
          </span>
        </div>
      );
    },
  },
  {
    header: "Failing episodes",
    cell: ({ row }) => {
      const ids = failing.get(row.original.scenario_id) ?? [];
      if (ids.length === 0) return <span className="text-muted-foreground">-</span>;
      const href = ids.length === 1 ? `/episodes/${ids[0]}` : `/runs/${runId}?outcome=failed`;
      return (
        <Button size="xs" variant="outline" render={<Link href={href} onClick={(e) => e.stopPropagation()} />}>
          {ids.length === 1 ? "Open episode" : `${ids.length} episodes`}
        </Button>
      );
    },
  },
];

export function ReportScenarioTable({ report, runId, failing }: { report: Report; runId: string; failing: Map<string, string[]> }) {
  const [facet, setFacet] = useState("all");
  const rows = [...report.per_scenario]
    .sort((a, b) => (a.rate ?? 1) - (b.rate ?? 1))
    .filter((r) => (facet === "failing" ? (r.rate ?? 1) < 1 : facet === "flaky" ? r.flaky || ((r.rate ?? 0) > 0 && (r.rate ?? 1) < 1) : true));
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium">Scenarios</h2>
        <ToggleGroup value={[facet]} onValueChange={(v) => v[0] && setFacet(v[0])} variant="outline" size="sm" aria-label="Scenario filter">
          <ToggleGroupItem value="all">All</ToggleGroupItem>
          <ToggleGroupItem value="failing">Failing</ToggleGroupItem>
          <ToggleGroupItem value="flaky">Flaky</ToggleGroupItem>
        </ToggleGroup>
      </div>
      <DataTable
        columns={columns(runId, failing)}
        data={rows}
        getRowId={(r) => r.scenario_id}
        rowTestId="scenario-row"
        emptyState={<p className="text-muted-foreground rounded-md border border-dashed p-3 text-sm">No scenarios match this filter.</p>}
      />
    </div>
  );
}
