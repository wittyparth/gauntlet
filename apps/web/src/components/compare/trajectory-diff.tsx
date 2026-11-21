"use client";

import { ErrorState } from "@/components/shared/error-state";
import { LoadingRows } from "@/components/shared/loading";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useEpisodeDiff } from "@/lib/api/hooks/compare";

/** Baseline on the left, candidate on the right, rows as the API aligned them. */
export function TrajectoryDiff({
  open,
  onOpenChange,
  episodeId,
  against,
  title,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  episodeId: string | null;
  against: string | null;
  title: string;
}) {
  const q = useEpisodeDiff(open ? episodeId : null, open ? against : null);
  const first = q.data?.first_divergence;
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-4xl" data-testid="trajectory-diff">
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>
            Baseline left, candidate right.{" "}
            {first ? `The trajectories first differ at baseline step ${first[0] ?? "-"} and candidate step ${first[1] ?? "-"}.` : q.data ? "The trajectories do not diverge." : ""}
          </SheetDescription>
        </SheetHeader>
        <ScrollArea className="min-h-0 flex-1 px-4">
          {q.isLoading ? <LoadingRows rows={6} /> : null}
          {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : null}
          {q.data ? (
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 pb-4 text-sm" role="table" aria-label="Trajectory comparison">
              {q.data.rows.map((r, i) => (
                <div key={i} className="contents" data-testid="diff-row">
                  <DiffCell seq={r.a_seq} kind={r.kind} text={r.summary_a} status={r.status} />
                  <DiffCell seq={r.b_seq} kind={r.kind} text={r.summary_b} status={r.status} />
                </div>
              ))}
              {q.data.truncated ? <p className="text-muted-foreground col-span-2 text-xs">The comparison was truncated.</p> : null}
            </div>
          ) : null}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}

function DiffCell({ seq, kind, text, status }: { seq: number | null; kind: string; text: string | null; status: string }) {
  const changed = status !== "same";
  return (
    <div className={`rounded-md border p-2 ${changed ? "border-warning/50 bg-warning/5" : ""}`}>
      <div className="mb-1 flex items-center gap-2">
        {seq != null ? <span className="text-muted-foreground font-mono text-xs">[{seq}]</span> : null}
        <Badge variant="outline">{kind}</Badge>
        {changed ? <Badge variant="secondary">{status}</Badge> : null}
      </div>
      <p className="break-words whitespace-pre-wrap">{text ?? <span className="text-muted-foreground">(none)</span>}</p>
    </div>
  );
}
