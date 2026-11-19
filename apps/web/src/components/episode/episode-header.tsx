"use client";

import Link from "next/link";

import { ChevronLeft } from "@/components/animate-ui/icons/chevron-left";
import { ChevronRight } from "@/components/animate-ui/icons/chevron-right";
import { EpisodeStatusBadge, OutcomeBadge } from "@/components/shared/badges";
import { CopyId } from "@/components/shared/copy-id";
import { Money } from "@/components/shared/live-number";
import { PageHeader } from "@/components/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { EpisodeDetail } from "@/lib/api/models";
import { formatDuration } from "@/lib/format";

export function EpisodeHeader({
  episode,
  runLabel,
  prevId,
  nextId,
}: {
  episode: EpisodeDetail;
  runLabel: string;
  prevId: string | null;
  nextId: string | null;
}) {
  const done = episode.status === "done" || episode.status === "cancelled";
  const turns = episode.events.filter((e) => e.kind === "user_message").length;
  const ms = episode.events.reduce((n, e) => n + e.wall_ms, 0);
  const goal = episode.scenario.goal;
  return (
    <>
      <PageHeader
        title={`${episode.scenario.title}`}
        breadcrumbs={[
          { label: "Runs", href: "/runs" },
          { label: runLabel, href: `/runs/${episode.run_id}` },
          { label: `${episode.scenario.title} · rep ${episode.rep + 1}` },
        ]}
        meta={
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {done ? <OutcomeBadge outcome={episode.outcome} /> : <EpisodeStatusBadge status={episode.status} />}
            {episode.termination ? <Badge variant="outline">{episode.termination}</Badge> : null}
            <span className="text-muted-foreground">{turns} {turns === 1 ? "turn" : "turns"}</span>
            <Money usdMicros={episode.cost_usd_micros} className="text-muted-foreground" />
            <span className="text-muted-foreground font-mono">{formatDuration(ms)}</span>
            <CopyId id={episode.id} />
          </div>
        }
        actions={
          <>
            <Button variant="outline" size="sm" disabled={!prevId} render={prevId ? <Link href={`/episodes/${prevId}`} /> : undefined} aria-label="Previous episode">
              <ChevronLeft size={14} /> Prev
            </Button>
            <Button variant="outline" size="sm" disabled={!nextId} render={nextId ? <Link href={`/episodes/${nextId}`} /> : undefined} aria-label="Next episode">
              Next <ChevronRight size={14} />
            </Button>
          </>
        }
      />
      <div className="border-b px-4 py-2 text-sm">
        {goal.length > 140 ? (
          <Collapsible>
            <CollapsibleTrigger render={<Button variant="ghost" size="xs" />}>Goal: {goal.slice(0, 140)}…</CollapsibleTrigger>
            <CollapsibleContent><p className="mt-1">{goal}</p></CollapsibleContent>
          </Collapsible>
        ) : (
          <span><span className="text-muted-foreground">Goal: </span>{goal}</span>
        )}
      </div>
    </>
  );
}
