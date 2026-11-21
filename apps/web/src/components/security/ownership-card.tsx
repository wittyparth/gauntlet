"use client";

import { Lock } from "@/components/animate-ui/icons/lock";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingCard } from "@/components/shared/loading";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useVerifications } from "@/lib/api/hooks/security";
import { timeAgo } from "@/lib/format";

/** Ownership verification of remote targets: only verified hosts can be attacked. */
export function OwnershipCard() {
  const q = useVerifications();
  if (q.isLoading) return <LoadingCard lines={1} />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const items = q.data.items;
  return (
    <Card size="sm" data-testid="ownership">
      <CardContent className="flex flex-col gap-2 p-3">
        <div className="flex items-center gap-2">
          <Lock size={14} />
          <h2 className="text-sm font-medium">Target ownership</h2>
        </div>
        {items.length === 0 ? (
          <p className="text-muted-foreground text-xs">
            No remote hosts verified. Local targets need no verification; a remote agent version cannot be attacked until its host is verified.
          </p>
        ) : (
          <ul className="flex flex-col gap-1">
            {items.map((v) => (
              <li key={v.id} className="flex items-center gap-2 text-xs">
                <span className="font-mono">{v.host}</span>
                <Badge variant="outline" className={v.status === "verified" ? "border-success/40 text-success" : "text-muted-foreground"}>
                  {v.status === "verified" ? "Verified" : v.status}
                </Badge>
                <span className="text-muted-foreground">
                  {v.verified_at ? `verified ${timeAgo(v.verified_at)}` : `via ${v.method}`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
