"use client";

import { useQuery } from "@tanstack/react-query";

import { bodyOf, client } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { qkQ } from "@/lib/query-keys";

type Schemas = components["schemas"];
export type MigrationReport = Schemas["MigrationReport"];
export type VersionSummary = Schemas["VersionSummary"];
export type ParetoOut = Schemas["ParetoOut"];
export type ParetoPoint = ParetoOut["points"][number];
export type Scorecard = Schemas["Scorecard"];

export function useMigrationReport(runId: string, baselineId: string, force = false) {
  return useQuery({
    queryKey: qkQ.migration(runId, baselineId, force),
    enabled: Boolean(runId && baselineId),
    retry: false,
    queryFn: async () =>
      bodyOf(
        await client.GET("/v1/runs/{run_id}/migration", {
          params: { path: { run_id: runId }, query: { baseline: baselineId, force } },
        }),
      ),
  });
}

export function usePareto(runIds: string[], force = false) {
  return useQuery({
    queryKey: qkQ.pareto(runIds),
    enabled: runIds.length >= 2,
    retry: false,
    queryFn: async () =>
      bodyOf(
        await client.GET("/v1/migrations/pareto", {
          params: { query: { run_ids: runIds.join(","), force } },
        }),
      ),
  });
}

export function useScorecard(agentId: string, versionId: string) {
  return useQuery({
    queryKey: qkQ.scorecard(agentId, versionId),
    enabled: Boolean(agentId && versionId),
    queryFn: async () =>
      bodyOf(
        await client.GET("/v1/agents/{agent_id}/versions/{version_id}/scorecard", {
          params: { path: { agent_id: agentId, version_id: versionId } },
        }),
      ),
  });
}
