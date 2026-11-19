"use client";

import Link from "next/link";
import { useState } from "react";

import { ExternalLink } from "@/components/animate-ui/icons/external-link";
import { Transcript, type TranscriptMode } from "@/components/episode/transcript";
import { EpisodeStatusBadge, OutcomeBadge } from "@/components/shared/badges";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingRows } from "@/components/shared/loading";
import { Button } from "@/components/ui/button";
import { useEpisode } from "@/lib/api/hooks/read";

import { useRunLive } from "./run-live-context";


export function LiveEpisodePanel({ episodeId }: { episodeId: string | null }) {
  if (!episodeId) {
    return (
      <div className="p-3">
        <EmptyState title="Select an episode to follow it" body="Click a row to see its transcript here." />
      </div>
    );
  }
  return <Panel key={episodeId} episodeId={episodeId} />;
}

function Panel({ episodeId }: { episodeId: string }) {
  const { pollMs } = useRunLive();
  const q = useEpisode(episodeId, { refetchInterval: pollMs });
  const [selected, setSelected] = useState<number | null>(null);
  const [mode, setMode] = useState<TranscriptMode>("all");
  if (q.isLoading) return <div className="p-3"><LoadingRows rows={6} /></div>;
  if (q.error) return <div className="p-3"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  const ep = q.data;
  if (!ep) return null;
  const done = ep.status === "done" || ep.status === "cancelled";
  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="live-episode-panel">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">{ep.scenario.title} · rep {ep.rep + 1}</div>
          <div className="mt-0.5">{done ? <OutcomeBadge outcome={ep.outcome} /> : <EpisodeStatusBadge status={ep.status} />}</div>
        </div>
        <Button size="sm" variant="outline" render={<Link href={`/episodes/${ep.id}`} />}>
          Open episode <ExternalLink size={12} />
        </Button>
      </div>
      {ep.events.length === 0 ? (
        <div className="p-3"><EmptyState title="This episode has not started" body="Events appear as soon as a worker picks it up." /></div>
      ) : (
        <Transcript
          events={ep.events}
          selectedSeq={selected}
          onSelect={setSelected}
          tools={ep.tools}
          live={!done}
          compact
          followBottom={!done}
          mode={mode}
          onModeChange={setMode}
        />
      )}
    </div>
  );
}
