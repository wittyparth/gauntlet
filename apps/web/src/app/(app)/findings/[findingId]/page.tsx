"use client";

import Link from "next/link";
import { use } from "react";

import { EvidenceEpisodes } from "@/components/findings/evidence-episodes";
import { FindingFacts, FindingHeader } from "@/components/findings/finding-header";
import { FindingNotesCard } from "@/components/findings/finding-notes-card";
import { ReproducerCard } from "@/components/findings/reproducer-card";
import { SuggestedRuleCard } from "@/components/findings/suggested-rule-card";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState, isNotFound } from "@/components/shared/error-state";
import { LoadingCard } from "@/components/shared/loading";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { useFinding } from "@/lib/api/hooks/findings";
import { useAllVersions } from "@/lib/api/hooks/security";

export default function FindingPage({ params }: { params: Promise<{ findingId: string }> }) {
  const { findingId } = use(params);
  const q = useFinding(findingId);
  const versions = useAllVersions();
  const f = q.data;

  if (q.isLoading) {
    return (
      <div aria-busy="true">
        <PageHeader title="Finding" breadcrumbs={[{ label: "Findings", href: "/findings" }, { label: findingId }]} />
        <div className="grid gap-3 p-4 lg:grid-cols-2">
          <LoadingCard lines={6} />
          <LoadingCard lines={8} />
        </div>
      </div>
    );
  }
  if (q.error || !f) {
    return (
      <>
        <PageHeader title="Finding" breadcrumbs={[{ label: "Findings", href: "/findings" }, { label: findingId }]} />
        <div className="p-4">
          {q.error && isNotFound(q.error) ? (
            <EmptyState
              title="Finding not found"
              body="It may have been removed, or the link is wrong."
              action={<Button render={<Link href="/findings" />}>Go to findings</Button>}
            />
          ) : (
            <ErrorState error={q.error} onRetry={() => q.refetch()} />
          )}
        </div>
      </>
    );
  }
  const match = versions.items.find((v) => v.version.id === f.agent_version_id);
  const versionLabel = match ? `${match.agentName} ${match.version.label}` : f.agent_version_id;
  return (
    <>
      <FindingHeader finding={f} />
      <div className="flex flex-col gap-3 p-4">
        <FindingFacts finding={f} versionLabel={versionLabel} />
        <div className="grid items-start gap-3 xl:grid-cols-2">
          <div className="flex flex-col gap-3">
            <ReproducerCard reproducer={f.reproducer} />
            {f.suggested_policy ? <SuggestedRuleCard rule={f.suggested_policy} /> : null}
            <FindingNotesCard finding={f} />
          </div>
          <EvidenceEpisodes episodes={f.episodes} />
        </div>
      </div>
    </>
  );
}
