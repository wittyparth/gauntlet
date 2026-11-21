"use client";

import { useSearchParams } from "next/navigation";
import { use } from "react";

import { BaselinePicker } from "@/components/compare/baseline-picker";
import { CompareSummary } from "@/components/compare/compare-summary";
import { FlipTable } from "@/components/compare/flip-table";
import { ReliabilityChart } from "@/components/runs/reliability-chart";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingCard, LoadingRows } from "@/components/shared/loading";
import { useRunComparison } from "@/lib/api/hooks/compare";
import { useRun, useRunReport } from "@/lib/api/hooks/read";

export default function ComparePage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params);
  const baseline = useSearchParams().get("baseline") ?? "";
  const run = useRun(runId);
  const cmp = useRunComparison(runId, baseline);
  const candReport = useRunReport(runId);
  const baseReport = useRunReport(baseline);
  const suiteId = run.data?.suite_id ?? "";
  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">{baseline ? `Comparing with ${baseline}` : "Compare"}</h2>
        {suiteId ? <BaselinePicker runId={runId} suiteId={suiteId} label="Change baseline" /> : null}
      </div>
      {!baseline ? (
        <EmptyState title="Choose a baseline run" body="Pick a finished run of the same suite to see what changed." action={suiteId ? <BaselinePicker runId={runId} suiteId={suiteId} variant="default" label="Choose baseline" /> : undefined} />
      ) : cmp.isLoading ? (
        <>
          <LoadingCard lines={2} />
          <LoadingRows rows={5} />
        </>
      ) : cmp.error ? (
        <ErrorState error={cmp.error} onRetry={() => cmp.refetch()} />
      ) : cmp.data && cmp.data.shared_scenarios === 0 ? (
        <EmptyState title="No shared scenarios" body="These runs have no scenario in common, so there is nothing to compare." />
      ) : cmp.data ? (
        <>
          <CompareSummary compare={cmp.data} baselineRate={baseReport.data?.pass_rate} runRate={candReport.data?.pass_rate} />
          {(candReport.data?.reliability.length ?? 0) > 0 || (baseReport.data?.reliability.length ?? 0) > 0 ? (
            <ReliabilityChart
              title="Reliability (pass^k, both runs)"
              series={[
                { key: "baseline", name: "Baseline", points: baseReport.data?.reliability ?? [], color: "var(--muted-foreground)" },
                { key: "candidate", name: "Candidate", points: candReport.data?.reliability ?? [], color: "var(--primary)" },
              ]}
            />
          ) : null}
          <FlipTable flips={cmp.data.flips} />
        </>
      ) : null}
    </div>
  );
}
