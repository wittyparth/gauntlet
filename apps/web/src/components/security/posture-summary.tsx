"use client";

import { LiveNumber } from "@/components/shared/live-number";
import { StatCard } from "@/components/shared/stat-card";
import { Card, CardContent } from "@/components/ui/card";
import type { Posture } from "@/lib/api/hooks/security";
import { formatPercent } from "@/lib/format";

const SEVERITIES = ["critical", "high", "medium", "low"] as const;

/** Grade with its basis, then the counts that decide it. */
export function PostureSummary({ posture }: { posture: Posture }) {
  const s = posture.summary;
  return (
    <section className="flex flex-col gap-3" aria-label="Posture summary">
      <div className="grid gap-3 lg:grid-cols-[minmax(0,18rem)_1fr]">
        <Card size="sm" data-testid="stat-grade">
          <CardContent className="flex items-start gap-4 p-3">
            <div className="flex flex-col">
              <span className="text-muted-foreground text-xs">Grade</span>
              <span className="text-5xl leading-none font-semibold tabular-nums" data-testid="grade">
                {posture.grade}
              </span>
            </div>
            <ul className="text-muted-foreground flex flex-col gap-1 pt-1 text-xs">
              {posture.grade_basis.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {SEVERITIES.map((sev) => (
            <StatCard
              key={sev}
              name={`open-${sev}`}
              label={`Open ${sev}`}
              value={<LiveNumber value={s.open_by_severity[sev] ?? 0} />}
            />
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          name="attack-success"
          label="Attack success rate"
          value={formatPercent(s.attack_success_rate)}
          hint="Successful attacks over all attacks run against this version"
        />
        <StatCard name="attacks-run" label="Attacks run" value={<LiveNumber value={s.attacks_run} />} />
        <StatCard name="verified" label="Verified fixed" value={<LiveNumber value={s.verified} />} />
        <StatCard name="accepted" label="Accepted risk" value={<LiveNumber value={s.accepted_risk} />} />
      </div>
    </section>
  );
}
