"use client";

import { SeverityBadge } from "@/components/shared/badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Proposal } from "@/lib/api/hooks/policies";
import { cn } from "@/lib/utils";

const ACTION_TONE: Record<string, string> = {
  block: "border-destructive/40 text-destructive",
  require_approval: "border-warning/40 text-warning",
  redact: "border-info/40 text-info",
  log: "text-muted-foreground",
};

/** The policy's clauses with their proposed rules; selecting one opens it in the form. */
export function RuleList({ proposals, selected, onSelect, onStatus }: { proposals: Proposal[]; selected: string | null; onSelect: (clauseId: string) => void; onStatus: (clauseId: string, status: "accepted" | "rejected") => void }) {
  return (
    <ul className="flex flex-col gap-1" data-testid="rule-list">
      {proposals.map((p) => (
        <li key={p.clause_id}>
          <div className={cn("flex flex-col gap-1 rounded-md border p-2", selected === p.clause_id && "bg-muted")} data-testid="rule-row" data-status={p.status}>
            <button type="button" className="flex flex-col gap-1 text-left" disabled={!p.rule} onClick={() => onSelect(p.clause_id)} aria-pressed={selected === p.clause_id}>
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm">{p.rule?.id ?? p.clause_id}</span>
                {p.rule ? <SeverityBadge severity={p.rule.severity} /> : null}
                {p.rule ? <Badge variant="outline" className={ACTION_TONE[p.rule.action]}>{p.rule.action.replace("_", " ")}</Badge> : <Badge variant="secondary">{p.klass}, no rule</Badge>}
                <Badge variant="secondary">{p.status}</Badge>
              </span>
              <span className="text-muted-foreground text-xs">{p.clause_text}</span>
            </button>
            {p.rule ? (
              <div className="flex gap-1">
                <Button size="xs" variant="outline" disabled={p.status === "accepted"} onClick={() => onStatus(p.clause_id, "accepted")}>Accept</Button>
                <Button size="xs" variant="ghost" disabled={p.status === "rejected"} onClick={() => onStatus(p.clause_id, "rejected")}>Reject</Button>
              </div>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  );
}
