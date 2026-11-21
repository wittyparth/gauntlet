"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, use, useState } from "react";

import { StartRunDialog } from "@/components/agents/start-run-dialog";
import { CompareSummary } from "@/components/compare/compare-summary";
import { FlipTable } from "@/components/compare/flip-table";
import { ParetoChart } from "@/components/migration/pareto-chart";
import { VersionPairPicker, type Pair } from "@/components/migration/version-pair-picker";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingCard } from "@/components/shared/loading";
import { PageHeader } from "@/components/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useMigrationReport, usePareto, type VersionSummary } from "@/lib/api/hooks/migration";
import { useAgent, useAgentVersions, useRunList, useSuiteList } from "@/lib/api/hooks/read";
import { toApiError } from "@/lib/api/errors";
import { formatPercent, formatUsd } from "@/lib/format";

const REC = {
  safe_to_migrate: { label: "Safe to migrate", tone: "border-success/50 text-success" },
  review: { label: "Review before migrating", tone: "border-warning/50 text-warning" },
  do_not_migrate: { label: "Do not migrate", tone: "border-destructive/50 text-destructive" },
} as const;

function SummaryCard({ title, s }: { title: string; s: VersionSummary }) {
  return (
    <Card size="sm" data-testid="version-summary">
      <CardContent className="flex flex-col gap-1 p-3 text-sm">
        <div className="text-muted-foreground text-xs">{title}</div>
        <div className="font-medium">{s.label}{s.model ? <span className="text-muted-foreground ml-2 font-mono text-xs">{s.model}</span> : null}</div>
        <div className="font-mono text-xs">pass {s.pass_rate != null ? formatPercent(s.pass_rate) : "n/a"} · cost/episode {formatUsd(s.cost_per_episode_usd_micros)} · p95 {s.latency_p95_ms ?? "n/a"} ms · {s.episodes} episodes</div>
      </CardContent>
    </Card>
  );
}

function Migration({ agentId }: { agentId: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const agent = useAgent(agentId);
  const versions = useAgentVersions(agentId);
  const suites = useSuiteList();
  const runs = useRunList();
  const [pair, setPair] = useState<Pair>({ base: params.get("base") ?? "", candidate: params.get("candidate") ?? "", suite: params.get("suite") ?? "" });
  const applied: Pair = { base: params.get("base") ?? "", candidate: params.get("candidate") ?? "", suite: params.get("suite") ?? "" };

  const latestDone = (version: string) =>
    (runs.data?.items ?? []).filter((r) => r.agent_version_id === version && r.suite_id === applied.suite && r.status === "done").sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const baseRun = applied.base ? latestDone(applied.base) : undefined;
  const candRun = applied.candidate ? latestDone(applied.candidate) : undefined;
  const chosen = Boolean(applied.base && applied.candidate && applied.suite);
  const report = useMigrationReport(candRun?.id ?? "", baseRun?.id ?? "");
  const pareto = usePareto(baseRun && candRun ? [baseRun.id, candRun.id] : []);
  const name = agent.data?.name ?? "Agent";
  const list = versions.data?.items ?? [];
  const missing = chosen && !runs.isLoading ? [!baseRun ? applied.base : null, !candRun ? applied.candidate : null].filter((v): v is string => Boolean(v)) : [];
  const apiErr = report.error ? toApiError(report.error) : null;

  return (
    <>
      <PageHeader title={`${name}: model migration`} breadcrumbs={[{ label: "Agents", href: "/agents" }, { label: name, href: `/agents/${agentId}` }, { label: "Migration" }]} />
      <div className="flex flex-col gap-4 p-4">
        <VersionPairPicker
          versions={list}
          suites={(suites.data?.items ?? []).map((s) => ({ id: s.id, name: s.name }))}
          value={pair}
          onChange={setPair}
          onGo={() => router.replace(`/agents/${agentId}/migration?base=${pair.base}&candidate=${pair.candidate}&suite=${pair.suite}`, { scroll: false })}
        />
        {!chosen ? (
          <EmptyState title="Choose two versions" body="Pick a baseline version, a candidate version and a suite that both have finished runs on." />
        ) : runs.isLoading ? (
          <LoadingCard lines={3} />
        ) : missing.length > 0 ? (
          <EmptyState
            title="A finished run is missing"
            body="Both versions need a finished run of this suite before they can be compared."
            action={<div className="flex gap-2">{missing.map((v) => <StartRunDialog key={v} agentVersionId={v} variant="outline" />)}</div>}
          />
        ) : report.isLoading ? (
          <LoadingCard lines={4} />
        ) : apiErr?.code === "incomparable_runs" ? (
          <EmptyState title="These runs are not like for like" body={apiErr.message} action={<Button render={<Link href={`/runs/${candRun?.id}/compare?baseline=${baseRun?.id}`} />}>Open the plain comparison</Button>} />
        ) : report.error ? (
          <ErrorState error={report.error} onRetry={() => report.refetch()} />
        ) : report.data ? (
          <>
            <Card className={`border ${REC[report.data.recommendation].tone}`} data-testid="recommendation">
              <CardContent className="flex flex-col gap-2 p-4">
                <Badge variant="outline" className={`w-fit ${REC[report.data.recommendation].tone}`}>{REC[report.data.recommendation].label}</Badge>
                <ul className="list-disc pl-5 text-sm">{report.data.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                <p className="text-muted-foreground text-xs">
                  Cost per episode {report.data.cost_change_pct != null ? `${report.data.cost_change_pct >= 0 ? "+" : ""}${report.data.cost_change_pct.toFixed(1)}%` : "n/a"}, latency p95 {report.data.latency_p95_change_pct != null ? `${report.data.latency_p95_change_pct >= 0 ? "+" : ""}${report.data.latency_p95_change_pct.toFixed(1)}%` : "n/a"}.
                </p>
              </CardContent>
            </Card>
            <div className="grid gap-3 md:grid-cols-2">
              <SummaryCard title="Baseline" s={report.data.baseline} />
              <SummaryCard title="Candidate" s={report.data.candidate} />
            </div>
            <CompareSummary compare={report.data.compare} baselineRate={report.data.baseline.pass_rate} runRate={report.data.candidate.pass_rate} />
            {pareto.data ? <ParetoChart data={pareto.data} /> : pareto.error ? <ErrorState error={pareto.error} onRetry={() => pareto.refetch()} /> : null}
            <FlipTable flips={report.data.compare.flips} />
          </>
        ) : null}
      </div>
    </>
  );
}

export default function MigrationPage({ params }: { params: Promise<{ agentId: string }> }) {
  const { agentId } = use(params);
  return (
    <Suspense fallback={<div className="p-4"><LoadingCard lines={3} /></div>}>
      <Migration agentId={agentId} />
    </Suspense>
  );
}
