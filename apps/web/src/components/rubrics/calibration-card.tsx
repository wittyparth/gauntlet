"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/shared/stat-card";
import { LoadingCard } from "@/components/shared/loading";
import type { Calibration } from "@/lib/api/hooks/rubrics";
import { formatPercent, formatUsd } from "@/lib/format";

type Agreement = { n?: number; accuracy?: number; precision?: number | null; recall?: number | null; kappa?: number; kappa_low?: number; kappa_high?: number };

const num = (v: number | null | undefined, f: (x: number) => string) => (v == null ? "n/a" : f(v));

/** The newest finished calibration, shown as the API stores it. */
export function CalibrationCard({ items, loading }: { items: Calibration[] | undefined; loading: boolean }) {
  if (loading) return <LoadingCard lines={2} />;
  const latest = (items ?? []).find((c) => c.status === "done");
  if (!latest) {
    return (
      <Card data-testid="calibration-card">
        <CardContent className="flex items-center gap-2 p-4 text-sm">
          <Badge variant="outline">not calibrated</Badge>
          <span className="text-muted-foreground">No finished calibration yet. Calibration needs labelled golden items for this rubric.</span>
        </CardContent>
      </Card>
    );
  }
  const small = ((latest.result as { small?: Agreement | null } | null)?.small ?? null) as Agreement | null;
  return (
    <Card data-testid="calibration-card">
      <CardHeader className="flex-row items-center gap-2">
        <CardTitle className="text-sm">Calibration</CardTitle>
        {latest.gating_allowed ? <Badge variant="outline" className="border-success/40 text-success">gating allowed</Badge> : <Badge variant="outline">gating not allowed</Badge>}
        {latest.stale ? <Badge variant="outline" className="border-warning/40 text-warning">stale</Badge> : null}
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          name="kappa"
          label="Cohen's kappa"
          value={num(small?.kappa, (x) => x.toFixed(2))}
          interval={small?.kappa_low != null && small.kappa_high != null ? `${small.kappa_low.toFixed(2)} to ${small.kappa_high.toFixed(2)}` : undefined}
        />
        <StatCard name="accuracy" label="Accuracy" value={num(small?.accuracy, (x) => formatPercent(x))} />
        <StatCard name="precision-recall" label="Precision / recall on fail" value={`${num(small?.precision, (x) => formatPercent(x))} / ${num(small?.recall, (x) => formatPercent(x))}`} />
        <StatCard name="labelled" label="Labelled items" value={latest.golden_count} />
        <StatCard name="threshold" label="Threshold" value={num(latest.threshold, (x) => x.toFixed(2))} />
        <StatCard name="cost" label="Calibration cost" value={formatUsd(latest.cost_usd_micros)} />
      </CardContent>
    </Card>
  );
}
