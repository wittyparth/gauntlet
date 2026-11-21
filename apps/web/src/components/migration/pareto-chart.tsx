"use client";

import { useState } from "react";
import { CartesianGrid, LabelList, Scatter, ScatterChart, XAxis, YAxis } from "recharts";

import { MigrationTable } from "@/components/migration/migration-table";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { ParetoOut } from "@/lib/api/hooks/migration";

const config = { pass_rate: { label: "Pass rate", color: "var(--primary)" } } satisfies ChartConfig;

/** Cost against pass rate, one labelled point per version; the frontier is a step line. */
export function ParetoChart({ data }: { data: ParetoOut }) {
  const [view, setView] = useState("chart");
  const pts = data.points
    .filter((p) => p.pass_rate != null)
    .map((p) => ({ label: p.label, cost: p.cost_per_episode_usd_micros / 1_000_000, rate: (p.pass_rate ?? 0) * 100, frontier: p.on_frontier }));
  const frontier = pts.filter((p) => p.frontier).sort((a, b) => a.cost - b.cost);
  const dominated = data.points.filter((p) => !p.on_frontier);
  return (
    <Card data-testid="pareto">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-sm">Cost and pass rate</CardTitle>
        <ToggleGroup value={[view]} onValueChange={(v) => v[0] && setView(v[0])} variant="outline" size="sm" aria-label="Pareto view">
          <ToggleGroupItem value="chart">Chart</ToggleGroupItem>
          <ToggleGroupItem value="table">Table</ToggleGroupItem>
        </ToggleGroup>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {view === "chart" ? (
          <ChartContainer config={config} className="h-64 w-full" role="img" aria-label="Scatter of cost per episode against pass rate, one point per agent version">
            <ScatterChart margin={{ left: 4, right: 40, top: 16, bottom: 8 }}>
              <CartesianGrid />
              <XAxis dataKey="cost" type="number" name="Cost per episode" tickFormatter={(v: number) => `$${v.toFixed(3)}`} domain={["auto", "auto"]} />
              <YAxis dataKey="rate" type="number" name="Pass rate" unit="%" domain={[0, 100]} width={44} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Scatter data={frontier} line={{ stroke: "var(--color-pass_rate)" }} lineType="joint" fill="var(--color-pass_rate)" isAnimationActive={false} legendType="none">
                <LabelList dataKey="label" position="top" fontSize={11} />
              </Scatter>
              <Scatter data={pts.filter((p) => !p.frontier)} fill="var(--muted-foreground)" isAnimationActive={false} legendType="none">
                <LabelList dataKey="label" position="top" fontSize={11} />
              </Scatter>
            </ScatterChart>
          </ChartContainer>
        ) : null}
        {view === "chart" ? (
          <p className="text-muted-foreground text-xs">
            Points on the frontier: {frontier.map((f) => f.label).join(", ") || "none"}. A dominated point has another version at least as good on every metric and better on one (point estimates).
          </p>
        ) : null}
        {dominated.map((p) => (
          <p key={p.run_id} className="flex flex-wrap items-center gap-2 text-sm">
            <span>{p.label} is dominated.</span>
            {p.dominance_supported ? <Badge variant="outline">interval supports it</Badge> : <Badge variant="outline" className="border-warning/40 text-warning">intervals overlap, not established</Badge>}
          </p>
        ))}
        {view === "table" ? <MigrationTable points={data.points} /> : null}
        {data.cautions.map((c) => <p key={c} className="text-muted-foreground text-xs">{c}</p>)}
      </CardContent>
    </Card>
  );
}
