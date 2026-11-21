"use client";

import Link from "next/link";

import { SeverityBadge } from "@/components/shared/badges";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { useClusters } from "@/lib/api/hooks/compare";

/** Failure clusters of a run, above the failures table. Renders nothing without clusters. */
export function ClusterList({ runId }: { runId: string }) {
  const q = useClusters(runId);
  const clusters = q.data?.clusters ?? [];
  if (clusters.length === 0) return null;
  return (
    <div className="flex flex-col gap-2" data-testid="cluster-list">
      <h2 className="text-sm font-medium">Failure clusters</h2>
      <Accordion className="rounded-md border">
        {clusters.map((c) => (
          <AccordionItem key={c.id} value={c.id} data-testid="cluster-row">
            <AccordionTrigger className="px-3">
              <span className="flex flex-wrap items-center gap-2">
                <span>{c.name}</span>
                <Badge variant="secondary">{c.size} {c.size === 1 ? "episode" : "episodes"}</Badge>
                {c.max_severity ? <SeverityBadge severity={c.max_severity} /> : null}
              </span>
            </AccordionTrigger>
            <AccordionContent className="flex flex-col gap-2 px-3">
              <p className="text-sm">{c.description}</p>
              <p className="text-muted-foreground text-xs">
                Likely root cause: <span className="text-foreground font-mono">{c.root_cause}</span> ({Math.round(c.root_cause_share * 100)}% of members)
              </p>
              <ul className="flex flex-wrap gap-2">
                {c.episode_ids.map((id) => (
                  <li key={id}>
                    <Link className="font-mono text-xs underline" href={`/episodes/${id}`}>{id}</Link>
                  </li>
                ))}
              </ul>
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  );
}
