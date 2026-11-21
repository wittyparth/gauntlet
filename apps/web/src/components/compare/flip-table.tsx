"use client";

import type { ColumnDef } from "@tanstack/react-table";
import { useState } from "react";

import { TrajectoryDiff } from "@/components/compare/trajectory-diff";
import { DataTable } from "@/components/shared/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Flip } from "@/lib/api/hooks/compare";
import { formatPercent } from "@/lib/format";

const TABS: { value: Flip["status"]; label: string }[] = [
  { value: "newly_failing", label: "Newly failing" },
  { value: "newly_passing", label: "Newly passing" },
  { value: "flaky", label: "Flaky" },
  { value: "stable", label: "Stable" },
];

function Rate({ rate, n }: { rate: number; n: number }) {
  return (
    <div className="flex items-center gap-2">
      <Progress value={rate * 100} className="w-20" aria-label="Pass rate" />
      <span className="font-mono text-xs">{formatPercent(rate)} <span className="text-muted-foreground">n={n}</span></span>
    </div>
  );
}

export function FlipTable({ flips }: { flips: Flip[] }) {
  const first = TABS.find((t) => flips.some((f) => f.status === t.value))?.value ?? "newly_failing";
  const [tab, setTab] = useState<string>(first);
  const [open, setOpen] = useState<Flip | null>(null);
  const rows = flips.filter((f) => f.status === tab);
  const columns: ColumnDef<Flip, unknown>[] = [
    { header: "Scenario", cell: ({ row }) => <span>{row.original.title}{row.original.single_trial ? <Badge variant="outline" className="ml-2">single trial</Badge> : null}</span> },
    { header: "Baseline", cell: ({ row }) => <Rate rate={row.original.rate_baseline} n={row.original.n_baseline} /> },
    { header: "Candidate", cell: ({ row }) => <Rate rate={row.original.rate_run} n={row.original.n_run} /> },
    { header: "p", cell: ({ row }) => <span className="font-mono text-xs">{row.original.p_value != null ? row.original.p_value.toFixed(3) : "-"}</span> },
    {
      header: "Diff",
      cell: ({ row }) =>
        row.original.episode_baseline && row.original.episode_run ? (
          <Button size="xs" variant="outline" onClick={(e) => { e.stopPropagation(); setOpen(row.original); }}>Compare trajectories</Button>
        ) : (
          <span className="text-muted-foreground">-</span>
        ),
    },
  ];
  return (
    <div className="flex flex-col gap-2" data-testid="flip-table">
      <h2 className="text-sm font-medium">Flips</h2>
      <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
        <TabsList>
          {TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>
              {t.label} <Badge variant="secondary" className="ml-1">{flips.filter((f) => f.status === t.value).length}</Badge>
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      <DataTable
        columns={columns}
        data={rows}
        getRowId={(f) => f.scenario_id}
        rowTestId="flip-row"
        emptyState={<p className="text-muted-foreground rounded-md border border-dashed p-3 text-sm">No scenarios in this group.</p>}
      />
      <TrajectoryDiff
        open={open != null}
        onOpenChange={(o) => !o && setOpen(null)}
        episodeId={open?.episode_run ?? null}
        against={open?.episode_baseline ?? null}
        title={open?.title ?? "Trajectory comparison"}
      />
    </div>
  );
}
