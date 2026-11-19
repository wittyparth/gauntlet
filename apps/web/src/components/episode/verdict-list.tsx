"use client";

import { useRef, useState } from "react";

import { EmptyState } from "@/components/shared/empty-state";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { Verdict } from "@/lib/api/models";

import { VerdictCard } from "./verdict-card";

type Filter = "all" | "fail" | "pass" | "other";

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];
const rank = (v: Verdict) => {
  const sev = SEVERITY_ORDER.indexOf(v.severity);
  const s = sev < 0 ? 9 : sev;
  if (v.result === "fail") return (v.hard_fail ? 0 : 10) + s;
  if (v.result === "error") return 30;
  if (v.result === "pass") return 40;
  return 50;
};

/** fail (hard first, then by severity), error, pass, na. */
export function sortVerdicts(vs: Verdict[]): Verdict[] {
  return [...vs].sort((a, b) => rank(a) - rank(b));
}

export function VerdictList({
  verdicts,
  done,
  activeEvidence,
  onSelectEvidence,
}: {
  verdicts: Verdict[];
  done: boolean;
  activeEvidence: { seq: number | null; quote: string | null };
  onSelectEvidence: (seq: number, quote: string | null) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const seen = useRef<Set<string> | null>(null);
  const key = (v: Verdict) => `${v.criterion}|${v.evaluator}|${v.stage}`;
  const first = seen.current === null;
  if (first) seen.current = new Set(verdicts.map(key));
  const fresh = new Set(verdicts.filter((v) => !seen.current?.has(key(v))).map(key));
  seen.current = new Set(verdicts.map(key));

  if (verdicts.length === 0) {
    return (
      <EmptyState
        title={done ? "No evaluators ran" : "No verdicts yet"}
        body={done ? "This episode ended without any rubric or check producing a verdict." : "Verdicts appear when the episode ends."}
      />
    );
  }
  const shown = sortVerdicts(verdicts).filter((v) =>
    filter === "all" ? true : filter === "other" ? v.result !== "fail" && v.result !== "pass" : v.result === filter,
  );
  return (
    <div className="flex flex-col gap-2">
      <ToggleGroup
        value={[filter]}
        onValueChange={(v) => v[0] && setFilter(v[0] as Filter)}
        variant="outline"
        size="sm"
        aria-label="Verdict filter"
      >
        <ToggleGroupItem value="all">All</ToggleGroupItem>
        <ToggleGroupItem value="fail">Fail</ToggleGroupItem>
        <ToggleGroupItem value="pass">Pass</ToggleGroupItem>
        <ToggleGroupItem value="other">Other</ToggleGroupItem>
      </ToggleGroup>
      {shown.map((v) => (
        <VerdictCard
          key={key(v)}
          verdict={v}
          activeEvidence={activeEvidence}
          onSelectEvidence={onSelectEvidence}
          animateIn={fresh.has(key(v))}
        />
      ))}
    </div>
  );
}
