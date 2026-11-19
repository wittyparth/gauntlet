"use client";

import { useSearchParams } from "next/navigation";
import { use, type ReactNode } from "react";

import { RunHeader } from "@/components/runs/run-header";
import { RunLiveContext } from "@/components/runs/run-live-context";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState, isNotFound } from "@/components/shared/error-state";
import { LoadingCard } from "@/components/shared/loading";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { useRun } from "@/lib/api/hooks/read";
import { isTerminalRun } from "@/lib/api/models";
import { useRunStream } from "@/lib/sse/use-run-stream";
import Link from "next/link";

export default function RunLayout({ children, params }: { children: ReactNode; params: Promise<{ runId: string }> }) {
  const { runId } = use(params);
  const focus = useSearchParams().get("episode");
  const run = useRun(runId);
  const live = Boolean(run.data && !isTerminalRun(run.data.status));
  const stream = useRunStream(runId, { enabled: live, focusedEpisodeId: focus });
  const pollMs = live && stream.status === "closed" ? 3000 : false;

  if (run.isLoading) {
    return (
      <div aria-busy="true">
        <PageHeader title="Run" breadcrumbs={[{ label: "Runs", href: "/runs" }, { label: runId }]} />
        <div className="flex flex-col gap-3 p-4"><LoadingCard lines={2} /></div>
      </div>
    );
  }
  if (run.error) {
    return (
      <>
        <PageHeader title="Run" breadcrumbs={[{ label: "Runs", href: "/runs" }, { label: runId }]} />
        <div className="p-4">
        {isNotFound(run.error) ? (
          <EmptyState title="Run not found" body="It may have been deleted, or the link is wrong." action={<Button render={<Link href="/runs" />}>Go to runs</Button>} />
        ) : (
          <ErrorState error={run.error} onRetry={() => run.refetch()} />
        )}
        </div>
      </>
    );
  }
  if (!run.data) return null;
  return (
    <RunLiveContext.Provider value={{ status: stream.status, pollMs, live }}>
      <div className="flex h-svh min-h-0 flex-col">
        <RunHeader run={run.data} />
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </RunLiveContext.Provider>
  );
}
