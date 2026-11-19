"use client";

import { TriangleAlert } from "@/components/animate-ui/icons/triangle-alert";
import { Money } from "@/components/shared/live-number";
import { StatCard } from "@/components/shared/stat-card";
import { Card, CardContent } from "@/components/ui/card";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import type { Report } from "@/lib/api/models";
import { formatPercent } from "@/lib/format";

export function ReportSummary({ report }: { report: Report }) {
  const excludedTotal = Object.values(report.excluded).reduce((a, b) => a + b, 0);
  const interval =
    report.ci_low != null && report.ci_high != null
      ? `(${formatPercent(report.ci_low)} to ${formatPercent(report.ci_high)})`
      : undefined;
  const cautions: string[] = [];
  if (report.caution?.self_preference) cautions.push("The judge model is from the same family as the agent, so scores may be inflated.");
  if (report.caution?.world_fidelity && report.caution.world_fidelity !== "full") cautions.push(`World fidelity is ${report.caution.world_fidelity}: some tool results were simulated.`);
  if (report.caution?.reduced_coverage) cautions.push("Coverage is reduced: some scenarios did not finish.");
  if (report.caution?.uncalibrated_rubrics.length)
    cautions.push(`Uncalibrated rubrics cannot fail a CI gate: ${report.caution.uncalibrated_rubrics.join(", ")}.`);
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatCard
          name="pass-rate"
          label="Pass rate"
          value={report.pass_rate != null ? formatPercent(report.pass_rate) : "n/a"}
          interval={interval}
          hint="95% interval, resampled by scenario"
        />
        <StatCard name="scenarios" label="Scenarios" value={report.per_scenario.length} />
        <StatCard name="counted" label="Episodes" value={<span>{report.counted} <span className="text-muted-foreground text-sm">counted</span></span>} />
        <HoverCard>
          <HoverCardTrigger render={<div />}>
            <StatCard name="excluded" label="Excluded" value={excludedTotal} />
          </HoverCardTrigger>
          <HoverCardContent className="w-56">
            <div className="text-xs font-medium">Excluded from pass rate</div>
            {excludedTotal === 0 ? (
              <p className="text-muted-foreground text-xs">Nothing was excluded.</p>
            ) : (
              <ul className="mt-1 text-xs">
                {Object.entries(report.excluded).map(([k, v]) => (
                  <li key={k} className="flex justify-between"><span>{k.replace(/_/g, " ")}</span><span className="font-mono">{v}</span></li>
                ))}
              </ul>
            )}
          </HoverCardContent>
        </HoverCard>
        <StatCard name="cost" label="Cost" value={<Money usdMicros={report.cost_usd_micros} />} />
      </div>
      {cautions.length > 0 ? (
        <Card size="sm" className="border-warning/50 border" data-testid="cautions">
          <CardContent className="flex flex-col gap-1">
            {cautions.map((c) => (
              <p key={c} className="text-warning flex items-start gap-2 text-xs">
                <TriangleAlert size={14} className="mt-0.5 shrink-0" /> {c}
              </p>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
