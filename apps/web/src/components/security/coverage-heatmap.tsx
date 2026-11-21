"use client";

import Link from "next/link";
import { useMemo } from "react";

import { heatStep } from "@/components/findings/finding-utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { CoverageCell } from "@/lib/api/hooks/security";
import { formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

const VECTOR_ORDER = ["user_turn", "document", "tool_result", "tool_description", "system_context"];

/** One hue, five steps of attack success rate. The number is always printed in the cell. */
const STEP_CLASS = [
  "",
  "bg-muted/40",
  "bg-destructive/15",
  "bg-destructive/30",
  "bg-destructive/50",
  "bg-destructive/70",
] as const;
const LEGEND = [
  { step: 1, label: "0%" },
  { step: 2, label: "up to 25%" },
  { step: 3, label: "up to 50%" },
  { step: 4, label: "up to 75%" },
  { step: 5, label: "over 75%" },
] as const;

function Cell({ cell, versionId }: { cell: CoverageCell | undefined; versionId: string }) {
  if (!cell || cell.attempts === 0) {
    return (
      <TableCell className="text-muted-foreground text-center text-xs" data-testid="heat-cell" data-state="untested">
        <span tabIndex={0} aria-label="not tested" className="rounded-sm px-1 focus-visible:ring-2 focus-visible:outline-none">
          not tested
        </span>
      </TableCell>
    );
  }
  const step = heatStep(cell.attempts, cell.successes);
  const detail = `${cell.successes} of ${cell.attempts} attacks succeeded, ${formatPercent(cell.rate)} (95% interval ${formatPercent(cell.ci_low)} to ${formatPercent(cell.ci_high)})`;
  const body = (
    <span className="flex flex-col items-center leading-tight">
      <span className="font-mono text-sm font-medium tabular-nums">
        {cell.successes}/{cell.attempts}
      </span>
      <span className="text-muted-foreground text-[11px] tabular-nums">{formatPercent(cell.rate)}</span>
    </span>
  );
  return (
    <TableCell
      className={cn("p-0 text-center", STEP_CLASS[step])}
      data-testid="heat-cell"
      data-state="tested"
      data-step={step}
    >
      <Tooltip>
        <TooltipTrigger
          render={
            cell.successes > 0 ? (
              <Link
                href={`/findings?category=${encodeURIComponent(cell.category)}&agent=${encodeURIComponent(versionId)}&status=all`}
                aria-label={`${cell.category}, ${cell.vector}: ${detail}. Open matching findings`}
                className="block px-2 py-1.5 focus-visible:ring-2 focus-visible:outline-none"
              />
            ) : (
              <span tabIndex={0} aria-label={`${cell.category}, ${cell.vector}: ${detail}`} className="block px-2 py-1.5 focus-visible:ring-2 focus-visible:outline-none" />
            )
          }
        >
          {body}
        </TooltipTrigger>
        <TooltipContent>{detail}</TooltipContent>
      </Tooltip>
    </TableCell>
  );
}

/** Categories by attack vector, from the coverage endpoint. Never invents a vector or category. */
export function CoverageHeatmap({
  cells,
  titles,
  versionId,
}: {
  cells: CoverageCell[];
  titles: Map<string, string>;
  versionId: string;
}) {
  const { categories, vectors, byKey } = useMemo(() => {
    const cats: string[] = [];
    const vecs = new Set<string>();
    const map = new Map<string, CoverageCell>();
    for (const c of cells) {
      if (!cats.includes(c.category)) cats.push(c.category);
      vecs.add(c.vector);
      map.set(`${c.category}|${c.vector}`, c);
    }
    const ordered = [...vecs].sort((a, b) => {
      const ia = VECTOR_ORDER.indexOf(a);
      const ib = VECTOR_ORDER.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
    return { categories: cats, vectors: ordered, byKey: map };
  }, [cells]);

  return (
    <Card size="sm" data-testid="coverage-heatmap">
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>
          <h2 className="text-sm font-medium">Coverage</h2>
        </CardTitle>
        <ul className="text-muted-foreground flex flex-wrap items-center gap-3 text-xs" aria-label="Attack success rate scale">
          {LEGEND.map((l) => (
            <li key={l.step} className="flex items-center gap-1.5">
              <span aria-hidden className={cn("border-border size-3 rounded-sm border", STEP_CLASS[l.step])} />
              {l.label}
            </li>
          ))}
          <li className="flex items-center gap-1.5">
            <span aria-hidden className="border-border size-3 rounded-sm border border-dashed" />
            not tested
          </li>
        </ul>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="h-9 text-xs">Category</TableHead>
                {vectors.map((v) => (
                  <TableHead key={v} className="h-9 text-center font-mono text-xs">
                    {v}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {categories.map((c) => (
                <TableRow key={c} data-testid="heat-row" className="h-9">
                  <TableCell className="py-1 text-xs font-medium">{titles.get(c) ?? c}</TableCell>
                  {vectors.map((v) => (
                    <Cell key={v} cell={byKey.get(`${c}|${v}`)} versionId={versionId} />
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <p className="text-muted-foreground mt-2 text-xs">
          Each cell is successful attacks over attempts. A cell with no attempts is not tested, which is different from zero.
        </p>
      </CardContent>
    </Card>
  );
}
