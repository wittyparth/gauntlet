import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function LoadingRows({ rows = 8 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-px" aria-busy="true" aria-label="Loading" data-testid="loading-rows">
      {Array.from({ length: Math.min(rows, 8) }, (_, i) => (
        <Skeleton key={i} className="h-9 w-full rounded-none" />
      ))}
    </div>
  );
}

export function LoadingCard({ lines = 3 }: { lines?: number }) {
  return (
    <Card aria-busy="true" aria-label="Loading" data-testid="loading-card">
      <CardContent className="flex flex-col gap-2 p-3">
        <Skeleton className="h-4 w-1/3" />
        {Array.from({ length: lines }, (_, i) => (
          <Skeleton key={i} className="h-3 w-full" />
        ))}
      </CardContent>
    </Card>
  );
}
