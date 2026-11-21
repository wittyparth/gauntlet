"use client";

import { useQuery } from "@tanstack/react-query";

import { bodyOf, client } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { qkQ } from "@/lib/query-keys";

type Schemas = components["schemas"];
export type CompareReport = Schemas["CompareReport"];
export type Flip = Schemas["Flip"];
export type TrajectoryDiff = Schemas["TrajectoryDiff"];
export type Cluster = Schemas["ClusterOut"];

export function useRunComparison(runId: string, baselineId: string) {
  return useQuery({
    queryKey: qkQ.compare(runId, baselineId),
    enabled: Boolean(runId && baselineId),
    queryFn: async () =>
      bodyOf(
        await client.GET("/v1/runs/{run_id}/compare", {
          params: { path: { run_id: runId }, query: { baseline: baselineId } },
        }),
      ),
  });
}

export function useEpisodeDiff(episodeId: string | null, against: string | null) {
  return useQuery({
    queryKey: qkQ.diff(episodeId ?? "", against ?? ""),
    enabled: Boolean(episodeId && against),
    queryFn: async () =>
      bodyOf(
        await client.GET("/v1/episodes/{episode_id}/diff", {
          params: { path: { episode_id: episodeId ?? "" }, query: { against: against ?? "" } },
        }),
      ),
  });
}

export function useClusters(runId: string) {
  return useQuery({
    queryKey: qkQ.clusters(runId),
    enabled: Boolean(runId),
    queryFn: async () =>
      bodyOf(await client.GET("/v1/runs/{run_id}/clusters", { params: { path: { run_id: runId } } })),
  });
}
