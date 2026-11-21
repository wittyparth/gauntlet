"use client";

import { CircleAlert } from "@/components/animate-ui/icons/circle-alert";
import { CircleCheck } from "@/components/animate-ui/icons/circle-check";
import { Info } from "@/components/animate-ui/icons/info";
import { TriangleAlert } from "@/components/animate-ui/icons/triangle-alert";
import { StatCard } from "@/components/shared/stat-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { CompareReport } from "@/lib/api/hooks/compare";
import { formatPercent, formatUsd } from "@/lib/format";

const VERDICTS = {
  regression: { label: "Regression", Icon: TriangleAlert, tone: "border-destructive/50 text-destructive" },
  improvement: { label: "Improvement", Icon: CircleCheck, tone: "border-success/50 text-success" },
  no_detectable_change: { label: "No detectable change", Icon: Info, tone: "border-border text-foreground" },
  inconclusive: { label: "Inconclusive", Icon: CircleAlert, tone: "border-warning/50 text-warning" },
} as const;

const points = (v: number) => `${v >= 0 ? "+" : "-"}${Math.abs(v * 100).toFixed(1)}`;

/** The verdict as the API returns it, with the numbers around it. Nothing is computed here. */
export function CompareSummary({
  compare,
  baselineRate,
  runRate,
}: {
  compare: CompareReport;
  baselineRate?: number | null;
  runRate?: number | null;
}) {
  const v = VERDICTS[compare.verdict];
  const sentence = `Pass rate changed ${points(compare.delta)} points (interval ${points(compare.ci_low)} to ${points(compare.ci_high)}) across ${compare.shared_scenarios} shared scenarios.`;
  return (
    <div className="flex flex-col gap-3" data-testid="compare-summary">
      <Card className={`border ${v.tone}`} data-testid="verdict-banner">
        <CardContent className="flex flex-col gap-1 p-4">
          <div className="flex items-center gap-2">
            <v.Icon size={18} aria-hidden />
            <Badge variant="outline" className={v.tone}>{v.label}</Badge>
          </div>
          <p className="text-foreground text-sm">{sentence}</p>
          {compare.detectable_effect_text ? <p className="text-sm font-medium" data-testid="detectable-effect">{compare.detectable_effect_text}</p> : null}
        </CardContent>
      </Card>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard name="delta" label="Pass rate change" value={`${points(compare.delta)} pts`} interval={`${points(compare.ci_low)} to ${points(compare.ci_high)}`} />
        <StatCard name="baseline-rate" label="Baseline" value={baselineRate != null ? formatPercent(baselineRate) : "n/a"} />
        <StatCard name="candidate-rate" label="Candidate" value={runRate != null ? formatPercent(runRate) : "n/a"} />
        <StatCard
          name="cost-delta"
          label="Cost per episode"
          value={compare.cost.delta_pct != null ? `${compare.cost.delta_pct >= 0 ? "+" : ""}${compare.cost.delta_pct.toFixed(1)}%` : "n/a"}
          interval={`${formatUsd(compare.cost.baseline_per_episode_usd_micros)} to ${formatUsd(compare.cost.run_per_episode_usd_micros)}`}
        />
      </div>
      {compare.cautions.length > 0 ? (
        <ul className="text-muted-foreground list-disc pl-5 text-xs">
          {compare.cautions.map((c) => <li key={c}>{c}</li>)}
        </ul>
      ) : null}
    </div>
  );
}
