"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, use, useMemo, useState } from "react";

import { LiveEpisodePanel } from "@/components/runs/live-episode-panel";
import { EpisodeTable } from "@/components/runs/episode-table";
import { useRunLive } from "@/components/runs/run-live-context";
import { StatCards } from "@/components/runs/stat-cards";
import { countsTowardStats } from "@/components/shared/badges";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { FilterBar } from "@/components/shared/filter-bar";
import { LoadingCard } from "@/components/shared/loading";
import { SplitPane } from "@/components/shared/split-pane";
import { LoaderCircle } from "@/components/animate-ui/icons/loader-circle";
import { useRun, useRunEpisodes, useScenarioMap } from "@/lib/api/hooks/read";
import type { EpisodeRow } from "@/lib/api/models";

const FACETS = [
  { value: "all", label: "All" },
  { value: "running", label: "Running" },
  { value: "failed", label: "Failed" },
  { value: "passed", label: "Passed" },
  { value: "excluded", label: "Excluded" },
];

function matches(e: EpisodeRow, facet: string) {
  switch (facet) {
    case "running":
      return e.status === "leased";
    case "failed":
      return e.outcome === "failed";
    case "passed":
      return e.outcome === "passed";
    case "excluded":
      return Boolean(e.outcome) && !countsTowardStats(e.outcome);
    default:
      return true;
  }
}

function Console({ runId }: { runId: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const { pollMs, live } = useRunLive();
  const run = useRun(runId, { refetchInterval: pollMs });
  const eps = useRunEpisodes(runId, { refetchInterval: pollMs });
  const titles = useScenarioMap();
  const [facet, setFacet] = useState(params.get("outcome") ?? "all");
  const [search, setSearch] = useState("");

  const list = useMemo(() => eps.data?.items ?? [], [eps.data]);
  const focus = params.get("episode") ?? list.find((e) => e.status === "leased")?.id ?? null;
  const shown = list.filter(
    (e) => matches(e, facet) && (titles.get(e.scenario_id) ?? e.scenario_id).toLowerCase().includes(search.toLowerCase()),
  );
  const setFocus = (id: string) => {
    const next = new URLSearchParams(params.toString());
    next.set("episode", id);
    router.replace(`/runs/${runId}?${next.toString()}`, { scroll: false });
  };

  return (
    <div className="flex h-full min-h-[34rem] flex-col gap-3 p-4">
      <h2 className="sr-only">Run progress</h2>
      {run.data ? <StatCards run={run.data} live={live} /> : run.error ? <ErrorState error={run.error} onRetry={() => run.refetch()} /> : <LoadingCard />}
      <div className="border-border min-h-0 flex-1 overflow-hidden rounded-md border">
        <SplitPane
          id="run-console"
          defaultLeft={55}
          left={
            <div className="flex h-full min-h-0 flex-col gap-2 overflow-y-auto p-2">
              <FilterBar facets={FACETS} facet={facet} onFacetChange={setFacet} search={search} onSearchChange={setSearch} searchLabel="Search scenarios" />
              {eps.error ? (
                <ErrorState error={eps.error} onRetry={() => eps.refetch()} />
              ) : (
                <EpisodeTable
                  episodes={shown}
                  titles={titles}
                  selectedId={focus}
                  isLoading={eps.isLoading}
                  live={live}
                  onSelect={(e) => setFocus(e.id)}
                  onOpen={(e) => router.push(`/episodes/${e.id}`)}
                  emptyState={
                    list.length === 0 ? (
                      <EmptyState icon={<LoaderCircle size={18} animate loop />} title="Episodes are being queued" body="Rows appear here as soon as the run starts." />
                    ) : (
                      <EmptyState title="No episodes match these filters" action={undefined} body="Clear the filter or the search box to see all episodes." />
                    )
                  }
                />
              )}
            </div>
          }
          right={<LiveEpisodePanel episodeId={focus} />}
        />
      </div>
    </div>
  );
}

export default function RunConsolePage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params);
  return (
    <Suspense>
      <Console runId={runId} />
    </Suspense>
  );
}
