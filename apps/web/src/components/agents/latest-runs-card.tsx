"use client";

import Link from "next/link";

import { RunStatusBadge } from "@/components/shared/badges";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingRows } from "@/components/shared/loading";
import { Money } from "@/components/shared/live-number";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useRunList } from "@/lib/api/hooks/read";
import { isTerminalRun } from "@/lib/api/models";
import { formatPercent, timeAgo } from "@/lib/format";

export function LatestRunsCard({ versionIds, startAction }: { versionIds: string[]; startAction: React.ReactNode }) {
  const q = useRunList();
  const runs = (q.data?.items ?? []).filter((r) => versionIds.includes(r.agent_version_id)).slice(0, 5);
  return (
    <Card size="sm">
      <CardHeader><CardTitle><h2 className="text-sm font-medium">Recent runs</h2></CardTitle></CardHeader>
      <CardContent>
        {q.isLoading ? (
          <LoadingRows rows={3} />
        ) : q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : runs.length === 0 ? (
          <EmptyState title="No runs yet" body="Run a suite to see how this agent does." action={startAction} />
        ) : (
          <ul className="flex flex-col">
            {runs.map((r) => {
              const passed = r.counts.by_outcome.passed ?? 0;
              const failed = r.counts.by_outcome.failed ?? 0;
              return (
                <li key={r.id}>
                  <Link
                    href={isTerminalRun(r.status) ? `/runs/${r.id}/report` : `/runs/${r.id}`}
                    data-testid="recent-run"
                    className="hover:bg-muted/50 flex items-center gap-3 rounded-md px-2 py-2"
                  >
                    <RunStatusBadge status={r.status} />
                    <span className="min-w-0 flex-1 truncate font-mono text-xs">{r.suite_id}</span>
                    <span className="font-mono text-xs">{passed + failed > 0 ? formatPercent(passed / (passed + failed)) : "n/a"}</span>
                    <Money usdMicros={r.spent_usd_micros} />
                    <span className="text-muted-foreground text-xs">{timeAgo(r.created_at)}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
