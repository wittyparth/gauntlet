"use client";

import Link from "next/link";

import { FindingStatusBadge } from "@/components/findings/status-badge";
import { reproText } from "@/components/findings/finding-utils";
import { SeverityBadge } from "@/components/shared/badges";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Posture } from "@/lib/api/hooks/security";

function Section({ title, testId, children }: { title: string; testId: string; children: React.ReactNode }) {
  return (
    <Card size="sm" data-testid={testId}>
      <CardHeader>
        <CardTitle>
          <h2 className="text-sm font-medium">{title}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function TopFindings({ findings }: { findings: Posture["top_findings"] }) {
  return (
    <Section title="Top findings" testId="top-findings">
      {findings.length === 0 ? (
        <p className="text-muted-foreground text-sm">No open findings for this version.</p>
      ) : (
        <ul className="flex flex-col">
          {findings.map((f) => (
            <li key={f.id}>
              <Link
                href={`/findings/${f.id}`}
                data-testid="top-finding"
                className="hover:bg-muted/50 flex items-center gap-3 rounded-md px-2 py-2"
              >
                <SeverityBadge severity={f.severity} />
                <span className="min-w-0 flex-1 truncate text-sm">{f.title}</span>
                <span className="text-muted-foreground font-mono text-xs">{f.category}</span>
                <span className="font-mono text-xs tabular-nums">{reproText(f.reproducibility)}</span>
                <FindingStatusBadge status={f.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

export function Recommendations({ items }: { items: Posture["recommendations"] }) {
  if (items.length === 0) return null;
  return (
    <Section title="Recommendations" testId="recommendations">
      <ol className="flex flex-col gap-2">
        {[...items]
          .sort((a, b) => a.priority - b.priority)
          .map((r) => (
            <li key={r.priority} className="flex gap-3 text-sm">
              <span className="text-muted-foreground w-5 font-mono text-xs">{r.priority}.</span>
              <div className="flex flex-col gap-1">
                <span>{r.text}</span>
                <span className="flex flex-wrap gap-1">
                  {r.finding_ids.map((id) => (
                    <Link key={id} href={`/findings/${id}`} className="text-muted-foreground hover:text-foreground font-mono text-xs underline">
                      {id.slice(0, 12)}
                    </Link>
                  ))}
                </span>
              </div>
            </li>
          ))}
      </ol>
    </Section>
  );
}

export function DataExposure({ rows }: { rows: Posture["data_exposure"] }) {
  return (
    <Section title="Data exposure" testId="data-exposure">
      {rows.length === 0 ? (
        <p className="text-muted-foreground text-sm">No canaries were planted in these attacks.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-xs">Canary</TableHead>
              <TableHead className="text-xs">Placement</TableHead>
              <TableHead className="text-right text-xs">Leaked</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.canary_id}>
                <TableCell className="font-mono text-xs">
                  {r.canary_id} <span className="text-muted-foreground">({r.kind})</span>
                </TableCell>
                <TableCell className="text-xs">{r.placement.replace(/_/g, " ")}</TableCell>
                <TableCell className="text-right font-mono text-xs tabular-nums">
                  {r.leaked_episodes}/{r.planted_episodes}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Section>
  );
}

export function ComplianceTable({ rows }: { rows: Posture["compliance"] }) {
  if (rows.length === 0) return null;
  return (
    <Section title="Framework coverage" testId="compliance">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="text-xs">Framework</TableHead>
            <TableHead className="text-xs">Item</TableHead>
            <TableHead className="text-right text-xs">Attempts</TableHead>
            <TableHead className="text-right text-xs">Findings</TableHead>
            <TableHead className="text-xs">Covered</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={`${r.framework}-${r.id}`}>
              <TableCell className="text-xs">{r.framework}</TableCell>
              <TableCell className="font-mono text-xs">{r.id}</TableCell>
              <TableCell className="text-right font-mono text-xs tabular-nums">{r.attempts}</TableCell>
              <TableCell className="text-right font-mono text-xs tabular-nums">{r.findings}</TableCell>
              <TableCell>
                <Badge variant="outline" className={r.covered ? "border-success/40 text-success" : "text-muted-foreground"}>
                  {r.covered ? "Covered" : "Not covered"}
                </Badge>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Section>
  );
}

export function PreviousVersion({ previous }: { previous: NonNullable<Posture["previous"]> }) {
  return (
    <p className="text-muted-foreground text-xs" data-testid="previous-version">
      Against the previous version (grade {previous.grade}): {previous.new} new, {previous.fixed} fixed, {previous.unchanged} unchanged.
    </p>
  );
}
