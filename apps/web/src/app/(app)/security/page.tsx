"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";

import { CoverageHeatmap } from "@/components/security/coverage-heatmap";
import { KillSwitchCard } from "@/components/security/kill-switch-card";
import { OwnershipCard } from "@/components/security/ownership-card";
import { PostureSummary } from "@/components/security/posture-summary";
import {
  ComplianceTable,
  DataExposure,
  PreviousVersion,
  Recommendations,
  TopFindings,
} from "@/components/security/posture-sections";
import { ToolPermissionTable } from "@/components/security/tool-permission-table";
import { VersionPicker } from "@/components/security/version-picker";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingCard, LoadingRows } from "@/components/shared/loading";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useTaxonomy } from "@/lib/api/hooks/attacks";
import { useFindingList } from "@/lib/api/hooks/findings";
import { useAllVersions, useCoverage, usePosture } from "@/lib/api/hooks/security";

function PostureBody({ agentId, versionId }: { agentId: string; versionId: string }) {
  const posture = usePosture(agentId, versionId);
  const coverage = useCoverage(agentId, versionId);
  const taxonomy = useTaxonomy();
  const titles = useMemo(() => new Map((taxonomy.data?.categories ?? []).map((c) => [c.id, c.title])), [taxonomy.data]);

  if (posture.isLoading) {
    return (
      <div className="flex flex-col gap-3" aria-busy="true">
        <LoadingCard lines={2} />
        <LoadingRows rows={6} />
      </div>
    );
  }
  if (posture.error || !posture.data) return <ErrorState error={posture.error} onRetry={() => posture.refetch()} />;
  const p = posture.data;
  if (p.summary.attacks_run === 0) {
    return (
      <EmptyState
        title="No attack runs for this version yet"
        body="Run a campaign to see its grade, coverage and the tools it misuses."
        action={<Button render={<Link href={`/security/campaigns/new?version=${versionId}`} />}>Launch a campaign</Button>}
      />
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <PostureSummary posture={p} />
      {p.previous ? <PreviousVersion previous={p.previous} /> : null}
      {coverage.error ? (
        <ErrorState error={coverage.error} onRetry={() => coverage.refetch()} />
      ) : coverage.isLoading || !coverage.data ? (
        <LoadingRows rows={6} />
      ) : (
        <CoverageHeatmap cells={coverage.data.coverage} titles={titles} versionId={versionId} />
      )}
      <div className="grid items-start gap-3 xl:grid-cols-2">
        <TopFindings findings={p.top_findings} />
        <Recommendations items={p.recommendations} />
      </div>
      <Card size="sm" data-testid="tool-permissions">
        <CardHeader>
          <CardTitle>
            <h2 className="text-sm font-medium">Tool permissions</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ToolPermissionTable tools={p.tool_review} />
        </CardContent>
      </Card>
      <div className="grid items-start gap-3 xl:grid-cols-2">
        <DataExposure rows={p.data_exposure} />
        <ComplianceTable rows={p.compliance} />
      </div>
      <p className="text-muted-foreground text-xs">Report generated {new Date(p.generated_at).toLocaleString()}.</p>
    </div>
  );
}

function Posture() {
  const router = useRouter();
  const params = useSearchParams();
  const versions = useAllVersions();
  const findings = useFindingList({ status: "all" });

  const requested = params.get("version");
  const fallback = useMemo(() => {
    const counts = new Map<string, number>();
    for (const f of findings.data?.items ?? []) counts.set(f.agent_version_id, (counts.get(f.agent_version_id) ?? 0) + 1);
    const best = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
    return versions.items.find((i) => i.version.id === best) ?? versions.items[0];
  }, [findings.data, versions.items]);
  const current = versions.items.find((i) => i.version.id === requested) ?? fallback;

  return (
    <>
      <PageHeader
        title="Security posture"
        breadcrumbs={[{ label: "Security" }, { label: "Posture" }]}
        meta={
          versions.items.length > 0 ? (
            <VersionPicker
              items={versions.items}
              value={current?.version.id ?? ""}
              onChange={(v) => router.replace(`/security?version=${v}`, { scroll: false })}
            />
          ) : null
        }
        actions={
          <>
            <Button size="sm" variant="outline" render={<Link href="/security/audit" />}>
              Audit log
            </Button>
            <Button size="sm" render={<Link href={`/security/campaigns/new${current ? `?version=${current.version.id}` : ""}`} />}>
              Launch campaign
            </Button>
          </>
        }
      />
      <div className="flex flex-col gap-3 p-4">
        <div className="grid gap-3 lg:grid-cols-2">
          <KillSwitchCard />
          <OwnershipCard />
        </div>
        {versions.error ? (
          <ErrorState error={versions.error} onRetry={versions.refetch} />
        ) : versions.isLoading ? (
          <LoadingCard lines={3} />
        ) : !current ? (
          <EmptyState
            title="No agent versions yet"
            body="Add an agent and a version, then launch a campaign against it."
            action={<Button render={<Link href="/onboarding" />}>Set up an agent</Button>}
          />
        ) : (
          <PostureBody key={current.version.id} agentId={current.agentId} versionId={current.version.id} />
        )}
      </div>
    </>
  );
}

export default function SecurityPage() {
  return (
    <Suspense>
      <Posture />
    </Suspense>
  );
}
