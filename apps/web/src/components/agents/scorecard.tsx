"use client";

import { AnimateUIProvider } from "@animate-ui/react/provider";
import Link from "next/link";

import { SeverityBadge } from "@/components/shared/badges";
import { CopyId } from "@/components/shared/copy-id";
import { StatCard } from "@/components/shared/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Scorecard as ScorecardData } from "@/lib/api/hooks/migration";
import { formatPercent } from "@/lib/format";

/** Single column, print friendly, and still: no motion on this page at all. */
export function Scorecard({ card, agentName }: { card: ScorecardData; agentName: string }) {
  const lr = card.latest_run;
  const hat = (k: number) => lr?.pass_hat_k.find((p) => p.k === k);
  const rate = lr?.pass_rate;
  return (
    <AnimateUIProvider reducedMotion="always">
      <article className="mx-auto flex max-w-3xl flex-col gap-4 p-4" data-testid="scorecard">
        <header className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 className="text-xl font-semibold">{agentName} <span className="text-muted-foreground font-mono text-base">{card.agent_version.label}</span></h2>
            <p className="text-muted-foreground text-xs">Generated {new Date(card.generated_at).toLocaleString()}{lr?.finished_at ? `, latest run finished ${new Date(lr.finished_at).toLocaleDateString()}` : ""}</p>
          </div>
          <div className="flex gap-2 print:hidden" data-print-hide>
            <Button size="sm" variant="outline" onClick={() => window.print()}>Print</Button>
            <CopyId id={typeof window !== "undefined" ? window.location.href : ""} />
          </div>
        </header>

        {lr ? (
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Results">
            <StatCard name="pass-rate" label="Pass rate" value={rate != null ? formatPercent(rate) : "n/a"} interval={lr.ci_low != null && lr.ci_high != null ? `${formatPercent(lr.ci_low)} to ${formatPercent(lr.ci_high)}` : undefined} />
            {[1, 3, 5].map((k) => {
              const p = hat(k);
              return p ? <StatCard key={k} name={`pass-hat-${k}`} label={`pass^${k}`} value={formatPercent(p.value)} /> : null;
            })}
            <StatCard name="cost" label="Cost per 1000 episodes" value={card.cost_per_1000_episodes_usd != null ? `$${card.cost_per_1000_episodes_usd.toFixed(2)}` : "n/a"} />
            <StatCard name="latency" label="Latency p95" value={card.latency_p95_ms != null ? `${card.latency_p95_ms} ms` : "n/a"} />
          </section>
        ) : (
          <Card>
            <CardContent className="flex items-center gap-3 p-4 text-sm" data-testid="scorecard-empty">
              Run a suite to produce a scorecard.
              <Button className="print:hidden" size="sm" render={<Link href="/runs" />}>Go to runs</Button>
            </CardContent>
          </Card>
        )}

        {card.dimensions.length > 0 ? (
          <Card>
            <CardHeader><CardTitle className="text-sm">Rubric results</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>Rubric</TableHead><TableHead>Score</TableHead><TableHead>Severity</TableHead><TableHead>Gating</TableHead></TableRow></TableHeader>
                <TableBody>
                  {card.dimensions.map((d) => (
                    <TableRow key={d.criterion} data-testid="rubric-row">
                      <TableCell className="font-mono text-xs">{d.criterion}</TableCell>
                      <TableCell className="font-mono text-xs">{d.score != null ? formatPercent(d.score) : "n/a"}</TableCell>
                      <TableCell><SeverityBadge severity={d.severity} /></TableCell>
                      <TableCell>{d.gating_allowed ? "allowed" : <span className="text-muted-foreground">not calibrated</span>}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        ) : null}

        {card.security ? (
          <Card>
            <CardHeader><CardTitle className="text-sm">Security</CardTitle></CardHeader>
            <CardContent className="flex flex-wrap items-center gap-3 text-sm">
              <Badge variant="outline">Grade {card.security.grade}</Badge>
              <span>Coverage {card.security.coverage_pct}%</span>
              {Object.entries(card.security.open_findings_by_severity).map(([sev, n]) => (
                <span key={sev} className="flex items-center gap-1"><SeverityBadge severity={sev} /> {n} open</span>
              ))}
              {Object.keys(card.security.open_findings_by_severity).length === 0 ? <span>No open findings</span> : null}
            </CardContent>
          </Card>
        ) : null}

        {card.trend.length > 0 ? (
          <Card>
            <CardHeader><CardTitle className="text-sm">Recent runs</CardTitle></CardHeader>
            <CardContent>
              <ul className="font-mono text-xs">
                {card.trend.map((t) => (
                  <li key={t.run_id}>{t.finished_at ? new Date(t.finished_at).toLocaleDateString() : "-"} {t.run_id} {t.pass_rate != null ? formatPercent(t.pass_rate) : "n/a"}</li>
                ))}
              </ul>
            </CardContent>
          </Card>
        ) : null}

        <p className="text-muted-foreground text-xs">Quarantined scenarios: {card.quarantined_scenarios}.</p>
        {card.caveats.length > 0 ? (
          <section aria-label="Caveats">
            <h3 className="text-sm font-medium">Caveats</h3>
            <ul className="text-muted-foreground list-disc pl-5 text-xs">{card.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
          </section>
        ) : null}
        {card.badge ? <p className="text-muted-foreground font-mono text-xs break-all print:hidden">Badge: {card.badge.markdown}</p> : null}
      </article>
    </AnimateUIProvider>
  );
}
