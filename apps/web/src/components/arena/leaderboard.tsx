"use client";

import { LiveNumber } from "@/components/shared/live-number";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useLeaderboard } from "@/lib/arena/hooks";

/** Best solve per handle: fewest turns, then least time. Shows handle, level, turns, time only. */
export function Leaderboard({ level }: { level: number }) {
  const q = useLeaderboard(level);
  if (q.isLoading) return <Skeleton className="h-24 w-full" />;
  if (q.isError) return <p role="alert" className="text-destructive text-sm">The leaderboard is not available right now.</p>;
  const rows = q.data?.items ?? [];
  if (rows.length === 0) return <p className="text-muted-foreground text-sm" data-testid="leaderboard-empty">No solves on level {level} yet.</p>;
  return (
    <Table data-testid="leaderboard">
      <TableHeader>
        <TableRow>
          <TableHead className="w-12">#</TableHead>
          <TableHead>Handle</TableHead>
          <TableHead className="text-right">Turns</TableHead>
          <TableHead className="text-right">Seconds</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={`${r.handle}-${r.level}`}>
            <TableCell className="tabular-nums">{r.rank}</TableCell>
            <TableCell className="font-mono">{r.handle}</TableCell>
            <TableCell className="text-right"><LiveNumber value={r.turns} /></TableCell>
            <TableCell className="text-right"><LiveNumber value={r.seconds} /></TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
