"use client";

import { LiveNumber, Money } from "@/components/shared/live-number";
import { StatCard } from "@/components/shared/stat-card";
import { Progress } from "@/components/ui/progress";
import type { Run } from "@/lib/api/models";
import { cn } from "@/lib/utils";

export function StatCards({ run, live }: { run: Run; live: boolean }) {
  const c = run.counts;
  const passed = c.by_outcome.passed ?? 0;
  const failed = c.by_outcome.failed ?? 0;
  const excluded = Object.entries(c.by_outcome)
    .filter(([k]) => k !== "passed" && k !== "failed")
    .reduce((n, [, v]) => n + v, 0);
  const finished = c.done + c.cancelled;
  const pct = c.total ? (finished / c.total) * 100 : 0;
  const budgetPct = run.budget_usd_micros ? (run.spent_usd_micros / run.budget_usd_micros) * 100 : 0;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <StatCard
        name="progress"
        label="Progress"
        value={
          <span className="inline-flex items-baseline gap-1">
            <LiveNumber value={finished} /> <span className="text-muted-foreground text-sm">/ {c.total}</span>
          </span>
        }
      >
        <span className="sr-only" role="status" aria-live="polite">{finished} of {c.total} episodes finished</span>
        <Progress value={pct} aria-label="Episodes finished" />
      </StatCard>
      <StatCard name="passed" label="Passed" value={<LiveNumber value={passed} />} />
      <StatCard
        name="failed"
        label="Failed"
        value={<LiveNumber value={failed} />}
        hint="Excluded outcomes do not count toward the pass rate"
      >
        <span className="text-muted-foreground text-xs">Excluded {excluded}</span>
      </StatCard>
      <StatCard
        name="cost"
        label="Cost"
        value={
          <span className="inline-flex items-baseline gap-1">
            <Money usdMicros={run.spent_usd_micros} live={live} />
            <span className="text-muted-foreground text-sm">
              / <Money usdMicros={run.budget_usd_micros} />
            </span>
          </span>
        }
      >
        <Progress value={Math.min(100, budgetPct)} aria-label="Budget used" className={cn(budgetPct > 80 && "[&_[data-slot=progress-indicator]]:bg-warning")} />
      </StatCard>
    </div>
  );
}
