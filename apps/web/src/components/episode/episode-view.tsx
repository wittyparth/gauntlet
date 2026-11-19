"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useHotkeys } from "react-hotkeys-hook";
import { useRouter } from "next/navigation";

import { LoadingCard, LoadingRows } from "@/components/shared/loading";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState, isNotFound } from "@/components/shared/error-state";
import { PageHeader } from "@/components/shared/page-header";
import { SplitPane } from "@/components/shared/split-pane";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { useEpisode, useRun, useRunEpisodes } from "@/lib/api/hooks/read";
import type { EpisodeDetail } from "@/lib/api/models";
import { useRunStream } from "@/lib/sse/use-run-stream";
import { useMediaQuery } from "@/lib/use-media-query";
import Link from "next/link";

import { buildDiff } from "./diff-entries";
import { EpisodeHeader } from "./episode-header";
import { useEventSelection } from "./selection";
import { StateDiff } from "./state-diff";
import { ToolTimeline } from "./tool-timeline";
import { Transcript, type TranscriptMode } from "./transcript";
import { VerdictList } from "./verdict-list";
import { isMessage } from "./payloads";

type Tab = "verdicts" | "tools" | "state";
const TABS: Tab[] = ["verdicts", "tools", "state"];

function readTab(): Tab {
  const t = new URLSearchParams(window.location.search).get("tab");
  return TABS.includes(t as Tab) ? (t as Tab) : "verdicts";
}

function Body({ episode, runLabel, prevId, nextId, live }: { episode: EpisodeDetail; runLabel: string; prevId: string | null; nextId: string | null; live: boolean }) {
  const [mode, setMode] = useState<TranscriptMode>("all");
  const [tab, setTabState] = useState<Tab>("verdicts");
  const [sheetOpen, setSheetOpen] = useState(false);
  const narrow = useMediaQuery("(max-width: 1023px)");
  const router = useRouter();

  useEffect(() => setTabState(readTab()), []);
  const setTab = useCallback((t: Tab) => {
    setTabState(t);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", t);
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  }, []);

  const events = episode.events;
  const seqs = useMemo(() => events.map((e) => e.seq), [events]);
  const byseq = useMemo(() => new Map(events.map((e) => [e.seq, e])), [events]);
  const sel = useEventSelection(seqs, {
    ensureVisible: (seq) => {
      const e = byseq.get(seq);
      if (e && !isMessage(e)) setMode("all");
    },
  });

  useHotkeys("[", () => prevId && router.push(`/episodes/${prevId}`), [prevId]);
  useHotkeys("]", () => nextId && router.push(`/episodes/${nextId}`), [nextId]);

  const diff = useMemo(() => buildDiff(episode.diff, events), [episode.diff, events]);
  const hasToolEvents = events.some((e) => e.kind === "tool_call");
  const done = episode.status === "done" || episode.status === "cancelled";

  const openState = (seq: number) => {
    setTab("state");
    sel.select(seq);
    setSheetOpen(narrow);
  };
  const selectEvidence = (seq: number, quote: string | null) => sel.select(seq, quote);

  const transcript = events.length === 0 && !done ? (
    <div className="p-3">
      <EmptyState title="This episode has not started" body="Events appear here as soon as the worker picks it up." />
    </div>
  ) : (
    <Transcript
      events={events}
      selectedSeq={sel.selectedSeq}
      quote={sel.quote}
      onSelect={(s) => sel.select(s)}
      tools={episode.tools}
      live={live}
      mode={mode}
      onModeChange={setMode}
      onOpenState={openState}
    />
  );

  const right = (
    <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="h-full min-h-0 gap-0">
      <div className="border-b px-3 py-2">
        <TabsList aria-label="Episode details">
          <TabsTrigger value="verdicts">Verdicts <Badge variant="secondary">{episode.verdicts.length}</Badge></TabsTrigger>
          <TabsTrigger value="tools">Tools <Badge variant="secondary">{events.filter((e) => e.kind === "tool_call").length}</Badge></TabsTrigger>
          <TabsTrigger value="state">{diff.source === "server" ? "State diff" : "State changes"} <Badge variant="secondary">{diff.entries.length}</Badge></TabsTrigger>
        </TabsList>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        <TabsContent value="verdicts">
          <VerdictList verdicts={episode.verdicts} done={done} activeEvidence={{ seq: sel.selectedSeq, quote: sel.quote }} onSelectEvidence={selectEvidence} />
        </TabsContent>
        <TabsContent value="tools">
          <ToolTimeline events={events} tools={episode.tools} selectedSeq={sel.selectedSeq} onSelect={(s) => sel.select(s)} />
        </TabsContent>
        <TabsContent value="state">
          <StateDiff view={diff} hasToolEvents={hasToolEvents} selectedSeq={sel.selectedSeq} onSelect={(s) => sel.select(s)} />
        </TabsContent>
      </div>
    </Tabs>
  );

  return (
    <div className="flex h-svh min-h-0 flex-col">
      <EpisodeHeader episode={episode} runLabel={runLabel} prevId={prevId} nextId={nextId} />
      {narrow ? (
        <>
          <div className="flex justify-end border-b px-3 py-1">
            <Button size="sm" variant="outline" onClick={() => setSheetOpen(true)}>Details</Button>
          </div>
          <div className="flex min-h-0 flex-1 flex-col">{transcript}</div>
          <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
            <SheetContent side="bottom" className="h-[70vh]">
              <SheetHeader><SheetTitle>Episode details</SheetTitle></SheetHeader>
              {right}
            </SheetContent>
          </Sheet>
        </>
      ) : (
        <SplitPane id="episode-viewer" left={<div className="flex h-full min-h-0 flex-col">{transcript}</div>} right={right} />
      )}
    </div>
  );
}

export function EpisodeView({ episodeId }: { episodeId: string }) {
  const [poll, setPoll] = useState(false);
  const q = useEpisode(episodeId, { refetchInterval: poll ? 3000 : false });
  const ep = q.data;
  const live = Boolean(ep && ep.status !== "done" && ep.status !== "cancelled");
  const stream = useRunStream(ep?.run_id ?? "", { enabled: live, focusedEpisodeId: episodeId });
  useEffect(() => setPoll(live && stream.status === "closed"), [live, stream.status]);

  const runId = ep?.run_id ?? "";
  const eps = useRunEpisodes(runId);
  const run = useRun(runId);
  const list = eps.data?.items ?? [];
  const idx = list.findIndex((e) => e.id === episodeId);
  const prevId = idx > 0 ? list[idx - 1].id : null;
  const nextId = idx >= 0 && idx < list.length - 1 ? list[idx + 1].id : null;

  if (q.isLoading) {
    return (
      <div aria-busy="true">
        <PageHeader title="Episode" breadcrumbs={[{ label: "Runs", href: "/runs" }, { label: "Episode" }]} />
        <div className="flex flex-col gap-3 p-4">
        <LoadingCard lines={1} />
        <div className="grid grid-cols-[3fr_2fr] gap-3">
          <LoadingRows rows={8} />
          <div className="flex flex-col gap-2"><LoadingCard /><LoadingCard /><LoadingCard /></div>
        </div>
        </div>
      </div>
    );
  }
  if (q.error) {
    return (
      <>
        <PageHeader title="Episode" breadcrumbs={[{ label: "Runs", href: "/runs" }, { label: "Episode" }]} />
        <div className="p-4">
        {isNotFound(q.error) ? (
          <EmptyState title="Episode not found" body="It may have been deleted, or the link is wrong." action={<Button render={<Link href="/runs" />}>Go to runs</Button>} />
        ) : (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        )}
        </div>
      </>
    );
  }
  if (!ep) return null;
  const runLabel = run.data ? run.data.suite_id : runId;
  return <Body episode={ep} runLabel={runLabel} prevId={prevId} nextId={nextId} live={live} />;
}
