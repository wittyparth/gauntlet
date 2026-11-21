"use client";

import Link from "next/link";

import { reproText, sortFindings } from "@/components/findings/finding-utils";
import { SeverityBadge } from "@/components/shared/badges";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingRows } from "@/components/shared/loading";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useFindingList } from "@/lib/api/hooks/findings";

/** Open security findings of one agent version, worst first. */
export function OpenFindingsCard({ versionId }: { versionId: string }) {
  const q = useFindingList({ status: "open", agent_version_id: versionId });
  const rows = sortFindings(q.data?.items ?? []);
  return (
    <Card size="sm" data-testid="open-findings-card">
      <CardHeader>
        <CardTitle>
          <h2 className="text-sm font-medium">
            Open findings {q.data ? <span className="text-muted-foreground font-mono text-xs">({rows.length})</span> : null}
          </h2>
        </CardTitle>
        <CardAction>
          <Button size="xs" variant="ghost" render={<Link href={`/findings?agent=${versionId}`} />}>
          View all
        </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {q.isLoading ? (
          <LoadingRows rows={3} />
        ) : q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState
            title="No open findings"
            body="Launch a campaign to attack this version and see what gets through."
            action={<Button variant="outline" size="sm" render={<Link href={`/security/campaigns/new?version=${versionId}`} />}>Launch campaign</Button>}
          />
        ) : (
          <ul className="flex flex-col">
            {rows.slice(0, 5).map((f) => (
              <li key={f.id}>
                <Link href={`/findings/${f.id}`} className="hover:bg-muted/50 flex items-center gap-3 rounded-md px-2 py-2">
                  <SeverityBadge severity={f.severity} />
                  <span className="min-w-0 flex-1 truncate text-sm">{f.title}</span>
                  <span className="font-mono text-xs tabular-nums">{reproText(f.reproducibility)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
