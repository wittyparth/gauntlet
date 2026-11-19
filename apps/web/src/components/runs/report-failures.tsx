"use client";

import type { ColumnDef } from "@tanstack/react-table";

import { OutcomeBadge } from "@/components/shared/badges";
import { DataTable } from "@/components/shared/data-table";
import { Badge } from "@/components/ui/badge";
import type { EpisodeRow, Report } from "@/lib/api/models";

type Row = Report["failures"][number] & { title: string; rep: number | null; outcome: string | null };

const columns: ColumnDef<Row, unknown>[] = [
  { header: "Scenario", cell: ({ row }) => <span>{row.original.title}{row.original.rep != null ? ` · rep ${row.original.rep + 1}` : ""}</span> },
  { header: "Outcome", cell: ({ row }) => <OutcomeBadge outcome={row.original.outcome ?? "failed"} /> },
  {
    header: "Failed criteria",
    cell: ({ row }) => (
      <div className="flex flex-wrap gap-1">
        {row.original.reasons.map((r) => (
          <Badge key={r} variant="outline" className="font-mono">{r}</Badge>
        ))}
      </div>
    ),
  },
];

export function ReportFailures({ report, episodes, titles }: { report: Report; episodes: EpisodeRow[]; titles: Map<string, string> }) {
  const byId = new Map(episodes.map((e) => [e.id, e]));
  const rows: Row[] = report.failures.map((f) => ({
    ...f,
    title: titles.get(f.scenario_id) ?? report.per_scenario.find((s) => s.scenario_id === f.scenario_id)?.title ?? f.scenario_id,
    rep: byId.get(f.episode_id)?.rep ?? null,
    outcome: byId.get(f.episode_id)?.outcome ?? null,
  }));
  return (
    <div className="flex flex-col gap-2">
      <h2 className="text-sm font-medium">Failures</h2>
      <DataTable
        columns={columns}
        data={rows}
        getRowId={(r) => r.episode_id}
        rowTestId="failure-row"
        rowHref={(r) => `/episodes/${r.episode_id}`}
        emptyState={<p className="text-muted-foreground rounded-md border border-dashed p-3 text-sm">No failed episodes.</p>}
      />
    </div>
  );
}
