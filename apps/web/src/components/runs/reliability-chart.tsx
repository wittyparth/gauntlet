"use client";

import { useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { Report } from "@/lib/api/models";
import { formatPercent } from "@/lib/format";

type Point = Report["reliability"][number];
export type ReliabilitySeries = { key: string; name: string; points: Point[]; color: string };

const pct = (v: number) => Math.round(v * 1000) / 10;

/** pass^k for k = 1..n with the interval as a band. The values come from the report as is. */
export function ReliabilityChart({ series, title = "Reliability (pass^k)" }: { series: ReliabilitySeries[]; title?: string }) {
  const [view, setView] = useState("chart");
  const ks = [...new Set(series.flatMap((s) => s.points.map((p) => p.k)))].sort((a, b) => a - b);
  const data = ks.map((k) => {
    const row: Record<string, number | number[]> = { k };
    for (const s of series) {
      const p = s.points.find((x) => x.k === k);
      if (p) {
        row[s.key] = pct(p.value);
        row[`${s.key}_band`] = [pct(p.ci_low), pct(p.ci_high)];
      }
    }
    return row;
  });
  const config: ChartConfig = Object.fromEntries(series.map((s) => [s.key, { label: s.name, color: s.color }]));
  const maxK = ks[ks.length - 1] ?? 1;
  return (
    <Card data-testid="reliability-chart">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-sm">{title}</CardTitle>
        <ToggleGroup value={[view]} onValueChange={(v) => v[0] && setView(v[0])} variant="outline" size="sm" aria-label="Reliability view">
          <ToggleGroupItem value="chart">Chart</ToggleGroupItem>
          <ToggleGroupItem value="table">Table</ToggleGroupItem>
        </ToggleGroup>
      </CardHeader>
      <CardContent>
        {view === "chart" ? (
          <ChartContainer
            config={config}
            className="h-56 w-full"
            role="img"
            aria-label={`${title}: share of scenarios that pass all of k repetitions, for k from 1 to ${maxK}`}
          >
            <ComposedChart data={data} margin={{ left: 4, right: 12, top: 8 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="k" type="number" domain={[1, Math.max(maxK, 2)]} allowDecimals={false} tickLine={false} />
              <YAxis domain={[0, 100]} tickFormatter={(v: number) => `${v}%`} width={40} tickLine={false} />
              <ChartTooltip content={<ChartTooltipContent />} />
              {series.map((s) => (
                <Area key={`${s.key}_band`} dataKey={`${s.key}_band`} stroke="none" fill={`var(--color-${s.key})`} fillOpacity={0.15} isAnimationActive={false} legendType="none" tooltipType="none" />
              ))}
              {series.map((s) => (
                <Line key={s.key} dataKey={s.key} stroke={`var(--color-${s.key})`} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
              ))}
            </ComposedChart>
          </ChartContainer>
        ) : (
          <Table data-testid="reliability-table">
            <TableHeader>
              <TableRow>
                <TableHead>k</TableHead>
                {series.map((s) => <TableHead key={s.key}>{s.name}</TableHead>)}
              </TableRow>
            </TableHeader>
            <TableBody>
              {ks.map((k) => (
                <TableRow key={k}>
                  <TableCell className="font-mono text-xs">{k}</TableCell>
                  {series.map((s) => {
                    const p = s.points.find((x) => x.k === k);
                    return (
                      <TableCell key={s.key} className="font-mono text-xs">
                        {p ? `${formatPercent(p.value, 1)} (${formatPercent(p.ci_low)} to ${formatPercent(p.ci_high)})` : "n/a"}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
