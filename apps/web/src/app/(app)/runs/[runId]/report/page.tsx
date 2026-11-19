"use client";

import Link from "next/link";
import { use, useEffect } from "react";

import { useRunLive } from "@/components/runs/run-live-context";
import { ReportFailures } from "@/components/runs/report-failures";
import { ReportScenarioTable } from "@/components/runs/report-scenario-table";
import { ReportSummary } from "@/components/runs/report-summary";
import { SeverityBadge } from "@/components/shared/badges";
import { DataTable } from "@/components/shared/data-table";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingCard, LoadingRows } from "@/components/shared/loading";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useRun, useRunEpisodes, useRunReport, useScenarioMap } from "@/lib/api/hooks/read";
import type { Report } from "@/lib/api/models";
import { isTerminalRun } from "@/lib/api/models";
import type { ColumnDef } from "@tanstack/react-table";

type Dim = Report["dimensions"][number];
const dimColumns: ColumnDef<Dim, unknown>[] = [
  { header: "Rubric", cell: ({ row }) => <span className="font-mono text-xs">{row.original.criterion}</span> },
  { header: "Pass", cell: ({ row }) => <span className="font-mono text-xs">{row.original.passed}</span> },
  { header: "Fail", cell: ({ row }) => <span className="font-mono text-xs">{row.original.failed}</span> },
  { header: "N/A", cell: ({ row }) => <span className="font-mono text-xs">{row.original.na}</span> },
  { header: "Error", cell: ({ row }) => <span className="font-mono text-xs">{row.original.error}</span> },
  { header: "Severity", cell: ({ row }) => <SeverityBadge severity={row.original.severity} /> },
];

export default function RunReportPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params);
  const { pollMs } = useRunLive();
  const run = useRun(runId, { refetchInterval: pollMs });
  const report = useRunReport(runId);
  const eps = useRunEpisodes(runId);
  const titles = useScenarioMap();
  const status = run.data?.status;
  const { refetch } = report;
  useEffect(() => {
    if (status && isTerminalRun(status)) void refetch();
  }, [status, refetch]);

  const active = run.data ? !isTerminalRun(run.data.status) : false;
  const failing = new Map<string, string[]>();
  for (const f of report.data?.failures ?? []) failing.set(f.scenario_id, [...(failing.get(f.scenario_id) ?? []), f.episode_id]);

  return (
    <div className="flex flex-col gap-4 p-4">
      <h2 className="sr-only">Run report</h2>
      {active ? (
        <Card size="sm" className="border-info/50 border">
          <CardContent className="flex items-center justify-between gap-2">
            <span className="text-sm">Run in progress, so this report is partial.</span>
            <Button size="sm" variant="outline" render={<Link href={`/runs/${runId}`} />}>Open the console</Button>
          </CardContent>
        </Card>
      ) : null}
      {report.isLoading ? (
        <>
          <div className="grid grid-cols-5 gap-3">{Array.from({ length: 5 }, (_, i) => <LoadingCard key={i} lines={1} />)}</div>
          <LoadingRows rows={6} />
        </>
      ) : report.error ? (
        <ErrorState error={report.error} onRetry={() => report.refetch()} />
      ) : report.data && report.data.counted === 0 && report.data.per_scenario.length === 0 ? (
        <EmptyState title="No episodes counted yet" body="Episodes that pass or fail appear here once they finish." />
      ) : report.data ? (
        <>
          <ReportSummary report={report.data} />
          {report.data.dimensions.length > 0 ? (
            <div className="flex flex-col gap-2">
              <h2 className="text-sm font-medium">Dimensions</h2>
              <DataTable columns={dimColumns} data={report.data.dimensions} getRowId={(d) => d.criterion} rowTestId="dimension-row" />
            </div>
          ) : null}
          <ReportScenarioTable report={report.data} runId={runId} failing={failing} />
          <ReportFailures report={report.data} episodes={eps.data?.items ?? []} titles={titles} />
        </>
      ) : null}
    </div>
  );
}
