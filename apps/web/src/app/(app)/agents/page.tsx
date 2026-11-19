"use client";

import Link from "next/link";

import { AgentTable } from "@/components/agents/agent-table";
import { Plus } from "@/components/animate-ui/icons/plus";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { useAgentList } from "@/lib/api/hooks/read";

export default function AgentsPage() {
  const q = useAgentList();
  return (
    <>
      <PageHeader
        title="Agents"
        breadcrumbs={[{ label: "Agents" }]}
        actions={
          <Button size="sm" render={<Link href="/onboarding" />}>
            <Plus size={14} animateOnHover /> New agent
          </Button>
        }
      />
      <div className="p-4">
        {q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : (
          <AgentTable
            agents={q.data?.items ?? []}
            isLoading={q.isLoading}
            emptyState={
              <EmptyState
                title="No agents yet"
                body="An agent is the thing you want to test. Describe it, point Gauntlet at it, and run your first suite."
                action={<Button render={<Link href="/onboarding" />}>Set up your first agent</Button>}
              />
            }
          />
        )}
      </div>
    </>
  );
}
