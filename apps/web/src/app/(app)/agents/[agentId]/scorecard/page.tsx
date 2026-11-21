"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, use } from "react";

import { Scorecard } from "@/components/agents/scorecard";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingCard } from "@/components/shared/loading";
import { PageHeader } from "@/components/shared/page-header";
import { useScorecard } from "@/lib/api/hooks/migration";
import { useAgent, useAgentVersions } from "@/lib/api/hooks/read";

function Body({ agentId }: { agentId: string }) {
  const params = useSearchParams();
  const agent = useAgent(agentId);
  const versions = useAgentVersions(agentId);
  const versionId = params.get("version") ?? agent.data?.latest_version_id ?? versions.data?.items[0]?.id ?? "";
  const card = useScorecard(agentId, versionId);
  const name = agent.data?.name ?? "Agent";
  return (
    <>
      <PageHeader title={`${name}: scorecard`} breadcrumbs={[{ label: "Agents", href: "/agents" }, { label: name, href: `/agents/${agentId}` }, { label: "Scorecard" }]} />
      {card.isLoading || versions.isLoading ? (
        <div className="p-4"><LoadingCard lines={5} /></div>
      ) : !versionId ? (
        <div className="p-4"><EmptyState title="No versions yet" body="Add a version and run a suite to produce a scorecard." /></div>
      ) : card.error ? (
        <div className="p-4"><ErrorState error={card.error} onRetry={() => card.refetch()} /></div>
      ) : card.data ? (
        <Scorecard card={card.data} agentName={name} />
      ) : null}
    </>
  );
}

export default function ScorecardPage({ params }: { params: Promise<{ agentId: string }> }) {
  const { agentId } = use(params);
  return (
    <Suspense fallback={<div className="p-4"><LoadingCard lines={4} /></div>}>
      <Body agentId={agentId} />
    </Suspense>
  );
}
