"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, use } from "react";

import { OpenFindingsCard } from "@/components/agents/open-findings-card";
import { LatestRunsCard } from "@/components/agents/latest-runs-card";
import { ProfileCard } from "@/components/agents/profile-card";
import { StartRunDialog } from "@/components/agents/start-run-dialog";
import { TargetCard } from "@/components/agents/target-card";
import { ToolInventory } from "@/components/agents/tool-inventory";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState, isNotFound } from "@/components/shared/error-state";
import { LoadingCard } from "@/components/shared/loading";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAgent, useAgentVersions } from "@/lib/api/hooks/read";

function Overview({ agentId }: { agentId: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const agent = useAgent(agentId);
  const versions = useAgentVersions(agentId);
  const list = versions.data?.items ?? [];
  const latest = agent.data?.latest_version_id ?? list[0]?.id ?? null;
  const versionId = params.get("version") ?? latest;
  const version = list.find((v) => v.id === versionId) ?? list[0];

  if (agent.error) {
    return (
      <>
        <PageHeader title="Agent" breadcrumbs={[{ label: "Agents", href: "/agents" }]} />
        <div className="p-4">
          {isNotFound(agent.error) ? (
            <EmptyState title="Agent not found" body="It may have been removed, or the link is wrong." action={<Button render={<Link href="/agents" />}>Go to agents</Button>} />
          ) : (
            <ErrorState error={agent.error} onRetry={() => agent.refetch()} />
          )}
        </div>
      </>
    );
  }
  const name = agent.data?.name ?? "Agent";
  return (
    <>
      <PageHeader
        title={name}
        breadcrumbs={[{ label: "Agents", href: "/agents" }, { label: name }]}
        meta={
          list.length > 0 ? (
            <Select items={list.map((v) => ({ value: v.id, label: v.label }))} value={version?.id ?? ""} onValueChange={(v) => router.replace(`/agents/${agentId}?version=${v}`, { scroll: false })}>
              <SelectTrigger size="sm" aria-label="Version" className="w-28"><SelectValue placeholder="version" /></SelectTrigger>
              <SelectContent>
                {list.map((v) => <SelectItem key={v.id} value={v.id}>{v.label}</SelectItem>)}
              </SelectContent>
            </Select>
          ) : null
        }
        actions={
          version ? (
            <>
              <DropdownMenu>
                <DropdownMenuTrigger render={<Button size="sm" variant="outline" />}>Reports</DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem render={<Link href={`/agents/${agentId}/scorecard?version=${version.id}`} />}>Scorecard</DropdownMenuItem>
                  <DropdownMenuItem render={<Link href={`/agents/${agentId}/migration`} />}>Model migration</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
              <StartRunDialog agentVersionId={version.id} />
            </>
          ) : null
        }
      />
      <div className="grid gap-3 p-4 lg:grid-cols-2">
        {versions.isLoading || agent.isLoading ? (
          <>
            <LoadingCard lines={4} /><LoadingCard lines={4} /><LoadingCard lines={4} /><LoadingCard lines={4} />
          </>
        ) : versions.error ? (
          <div className="lg:col-span-2"><ErrorState error={versions.error} onRetry={() => versions.refetch()} /></div>
        ) : !version ? (
          <div className="lg:col-span-2"><EmptyState title="No versions yet" body="Add a version to describe how Gauntlet reaches this agent." action={<Button render={<Link href="/onboarding" />}>Set up a version</Button>} /></div>
        ) : (
          <>
            <ProfileCard profile={version.profile} />
            <ToolInventory worldId={version.world_id} allowed={version.target.kind === "hosted" ? version.target.tools : undefined} />
            <TargetCard target={version.target} />
            <LatestRunsCard versionIds={list.map((v) => v.id)} startAction={<StartRunDialog agentVersionId={version.id} variant="outline" />} />
            <OpenFindingsCard versionId={version.id} />
          </>
        )}
      </div>
    </>
  );
}

export default function AgentPage({ params }: { params: Promise<{ agentId: string }> }) {
  const { agentId } = use(params);
  return (
    <Suspense>
      <Overview agentId={agentId} />
    </Suspense>
  );
}
