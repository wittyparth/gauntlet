"use client";

import { ErrorState } from "@/components/shared/error-state";
import { EmptyState } from "@/components/shared/empty-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useBenchmarks, type Study } from "@/lib/api/hooks/benchmarks";

const fmt = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(3));

function StudyCard({ study }: { study: Study }) {
  const names = Object.keys(study.metrics).sort();
  return (
    <Card data-testid={`study-${study.name}`}>
      <CardHeader className="flex flex-row flex-wrap items-center gap-2">
        <CardTitle className="font-mono text-base">{study.name}</CardTitle>
        <Badge variant="outline">n = {study.n}</Badge>
        <Badge variant="outline">seed {study.seed}</Badge>
        <Badge variant="outline">v{study.platform_version}</Badge>
        {study.smoke ? <Badge variant="secondary">smoke run</Badge> : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Metric</TableHead>
              <TableHead className="text-right">Value</TableHead>
              <TableHead className="text-right">Interval</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {names.map((m) => {
              const iv = study.intervals?.[m];
              return (
                <TableRow key={m}>
                  <TableCell className="font-mono">{m}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{fmt(study.metrics[m])}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums" data-testid={`interval-${m}`}>
                    {iv ? `[${fmt(iv[0])}, ${fmt(iv[1])}]` : "no interval"}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        <div>
          <h3 className="text-sm font-medium">Limitations</h3>
          <ul className="text-muted-foreground list-disc pl-5 text-sm" data-testid="limitations">
            {study.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </div>
        {study.notes ? <p className="text-muted-foreground text-sm">{study.notes}</p> : null}
      </CardContent>
    </Card>
  );
}

export function BenchmarksPage() {
  const q = useBenchmarks();
  if (q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  const studies = q.data?.studies ?? [];
  if (studies.length === 0) {
    return <EmptyState title="No results published yet" body="Study results appear here once they are committed to the repository." />;
  }
  return (
    <div className="flex flex-col gap-4">
      {studies.map((s) => (
        <StudyCard key={s.name} study={s} />
      ))}
    </div>
  );
}
