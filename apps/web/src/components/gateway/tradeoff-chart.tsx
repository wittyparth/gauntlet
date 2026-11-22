"use client";

import { useState } from "react";
import { CartesianGrid, LabelList, Line, LineChart, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { PolicyTestReport } from "@/lib/api/hooks/policies";
import { formatPercent } from "@/lib/format";

const config = { block: { label: "Block rate", color: "var(--primary)" } } satisfies ChartConfig;

/** x = false-positive rate, y = block rate, one point per rule added in the API's greedy order. */
export function TradeoffChart({ rows }: { rows: PolicyTestReport["tradeoff"] }) {
  const [view, setView] = useState("chart");
  const data = rows.map((r) => ({ added: r.added, fp: Math.round(r.fp_rate * 1000) / 10, block: Math.round(r.block_rate * 1000) / 10 }));
  return (
    <Card data-testid="tradeoff">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-sm">Tradeoff: each rule added in turn</CardTitle>
        <ToggleGroup value={[view]} onValueChange={(v) => v[0] && setView(v[0])} variant="outline" size="sm" aria-label="Tradeoff view">
          <ToggleGroupItem value="chart">Chart</ToggleGroupItem>
          <ToggleGroupItem value="table">Table</ToggleGroupItem>
        </ToggleGroup>
      </CardHeader>
      <CardContent>
        {view === "chart" ? (
          <ChartContainer config={config} className="h-56 w-full" role="img" aria-label="Block rate against false-positive rate as each rule is added">
            <LineChart data={data} margin={{ left: 4, right: 40, top: 16 }}>
              <CartesianGrid />
              <XAxis dataKey="fp" type="number" unit="%" domain={[0, "auto"]} name="False-positive rate" />
              <YAxis dataKey="block" type="number" unit="%" domain={[0, 100]} width={44} name="Block rate" />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Line dataKey="block" stroke="var(--color-block)" strokeWidth={2} dot={{ r: 4 }} isAnimationActive={false}>
                <LabelList dataKey="added" position="top" fontSize={11} />
              </Line>
            </LineChart>
          </ChartContainer>
        ) : (
          <Table data-testid="tradeoff-table">
            <TableHeader>
              <TableRow><TableHead>Rule added</TableHead><TableHead>Blocked</TableHead><TableHead>False positives</TableHead><TableHead>Block rate</TableHead><TableHead>False-positive rate</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.added}>
                  <TableCell className="font-mono text-xs">{r.added}</TableCell>
                  <TableCell className="font-mono text-xs">{r.blocked}</TableCell>
                  <TableCell className="font-mono text-xs">{r.false_positives}</TableCell>
                  <TableCell className="font-mono text-xs">{formatPercent(r.block_rate)}</TableCell>
                  <TableCell className="font-mono text-xs">{formatPercent(r.fp_rate)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
