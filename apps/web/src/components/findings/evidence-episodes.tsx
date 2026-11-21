"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ExternalLink } from "@/components/animate-ui/icons/external-link";
import { Transcript, type TranscriptMode } from "@/components/episode/transcript";
import { useEventSelection } from "@/components/episode/selection";
import { CopyId } from "@/components/shared/copy-id";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingRows } from "@/components/shared/loading";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useEpisode } from "@/lib/api/hooks/read";
import type { EpisodeDetail } from "@/lib/api/models";
import type { FindingDetail } from "@/lib/api/hooks/findings";

type EpisodeLink = FindingDetail["episodes"][number];

/** The objective's own evidence quote for the first cited event, when the episode has it. */
function evidenceFor(episode: EpisodeDetail, link: EpisodeLink): { seq: number; quote: string | null } | null {
  for (const e of episode.events) {
    if (e.kind !== "check_result" || e.payload.check_id !== "objective") continue;
    const ev = e.payload.evidence;
    if (Array.isArray(ev)) {
      for (const item of ev) {
        if (typeof item === "object" && item !== null && "seq" in item && typeof item.seq === "number") {
          const quote = "quote" in item && typeof item.quote === "string" ? item.quote : null;
          return { seq: item.seq, quote };
        }
      }
    }
  }
  const seq = link.evidence_seqs[0];
  return seq === undefined ? null : { seq, quote: null };
}

function EpisodePane({ link }: { link: EpisodeLink }) {
  const q = useEpisode(link.episode_id);
  const [mode, setMode] = useState<TranscriptMode>("all");
  const events = useMemo(() => q.data?.events ?? [], [q.data]);
  const seqs = useMemo(() => events.map((e) => e.seq), [events]);
  const sel = useEventSelection(seqs);
  const { select } = sel;
  const evidence = q.data ? evidenceFor(q.data, link) : null;
  const evidenceSeq = evidence?.seq;
  const evidenceQuote = evidence?.quote ?? null;

  useEffect(() => {
    if (evidenceSeq !== undefined) select(evidenceSeq, evidenceQuote);
    // Preselect once per episode load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [link.episode_id, evidenceSeq, seqs.length]);

  if (q.isLoading) return <LoadingRows rows={6} />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return null;
  const href = `/episodes/${link.episode_id}${evidenceSeq !== undefined ? `#e-${evidenceSeq}` : ""}`;
  return (
    <div className="flex min-h-0 flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs">
          <CopyId id={link.episode_id} />
          <span className="text-muted-foreground">
            {link.evidence_seqs.length > 0 ? `cites event ${link.evidence_seqs.map((s) => `[${s}]`).join(" ")}` : "no cited event"}
          </span>
        </div>
        <Button size="xs" variant="outline" render={<Link href={href} />}>
          Open episode <ExternalLink size={12} animateOnHover />
        </Button>
      </div>
      <div className="flex max-h-[34rem] min-h-72 flex-col overflow-hidden rounded-md border" data-testid="evidence-transcript">
        <Transcript
          events={events}
          selectedSeq={sel.selectedSeq}
          quote={sel.quote}
          onSelect={(s) => sel.select(s)}
          tools={q.data.tools}
          compact
          mode={mode}
          onModeChange={setMode}
        />
      </div>
    </div>
  );
}

const ROLE_LABEL: Record<string, string> = {
  evidence: "Evidence",
  variant: "Variant",
  verification: "Verification",
  replay: "Replay",
};

/** The episodes behind the finding, with the cited event selected and highlighted. */
export function EvidenceEpisodes({ episodes }: { episodes: EpisodeLink[] }) {
  const [active, setActive] = useState(episodes[0]?.episode_id ?? "");
  const link = episodes.find((e) => e.episode_id === active) ?? episodes[0];
  return (
    <Card size="sm" data-testid="evidence-episodes">
      <CardHeader>
        <CardTitle>
          <h2 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">Evidence episode</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {!link ? (
          <EmptyState title="No episodes linked" body="This finding has no episodes yet. Replay it to produce some." />
        ) : (
          <>
            {episodes.length > 1 ? (
              <ToggleGroup
                value={[link.episode_id]}
                onValueChange={(v) => v[0] && setActive(v[0])}
                variant="outline"
                size="sm"
                aria-label="Episode"
                className="flex-wrap"
              >
                {episodes.map((e) => (
                  <ToggleGroupItem key={e.episode_id} value={e.episode_id}>
                    {ROLE_LABEL[e.role] ?? e.role} <span className="font-mono text-xs">{e.episode_id.slice(-4)}</span>
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            ) : null}
            <EpisodePane key={link.episode_id} link={link} />
          </>
        )}
      </CardContent>
    </Card>
  );
}
