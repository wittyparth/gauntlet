"use client";

import { useQuery } from "@tanstack/react-query";

import { bodyOf, client } from "@/lib/api/client";
import { qk } from "@/lib/query-keys";

const LIMIT = 200;

export function useProjectList() {
  return useQuery({
    queryKey: qk.projects,
    queryFn: async () =>
      bodyOf(await client.GET("/v1/projects", { params: { query: {} } })),
  });
}

export function useCurrentProject() {
  const q = useProjectList();
  return { ...q, project: q.data?.items[0] ?? null };
}

export function useAgentList() {
  return useQuery({
    queryKey: qk.agents,
    queryFn: async () =>
      bodyOf(await client.GET("/v1/agents", { params: { query: { limit: LIMIT } } })),
  });
}

export function useAgent(agentId: string) {
  return useQuery({
    queryKey: qk.agent(agentId),
    queryFn: async () =>
      bodyOf(await client.GET("/v1/agents/{agent_id}", { params: { path: { agent_id: agentId } } })),
  });
}

export function useAgentVersions(agentId: string) {
  return useQuery({
    queryKey: qk.agentVersions(agentId),
    queryFn: async () =>
      bodyOf(
          await client.GET("/v1/agents/{agent_id}/versions", {
            params: { path: { agent_id: agentId }, query: { limit: LIMIT } },
          }),
        ),
  });
}

export function useScenarioList() {
  return useQuery({
    queryKey: qk.scenarios,
    queryFn: async () =>
      bodyOf(await client.GET("/v1/scenarios", { params: { query: { limit: LIMIT } } })),
  });
}

export function useScenario(scenarioId: string) {
  return useQuery({
    queryKey: qk.scenario(scenarioId),
    queryFn: async () =>
      bodyOf(
          await client.GET("/v1/scenarios/{scenario_id}", {
            params: { path: { scenario_id: scenarioId } },
          }),
        ),
  });
}

/** scenario id -> title, for joining episode rows to names. */
export function useScenarioMap() {
  const q = useScenarioList();
  const map = new Map<string, string>();
  for (const r of q.data?.items ?? []) map.set(r.id, r.scenario.title);
  return map;
}

export function useSuiteList() {
  return useQuery({
    queryKey: qk.suites,
    queryFn: async () =>
      bodyOf(await client.GET("/v1/suites", { params: { query: { limit: LIMIT } } })),
  });
}

export function useWorld(worldId: string | null | undefined) {
  return useQuery({
    queryKey: qk.world(worldId ?? ""),
    enabled: Boolean(worldId),
    queryFn: async () =>
      bodyOf(
          await client.GET("/v1/worlds/{doc_id}", {
            params: { path: { doc_id: worldId ?? "" }, query: {} },
          }),
        ),
  });
}

export function useWorldList() {
  return useQuery({
    queryKey: qk.worlds,
    queryFn: async () =>
      bodyOf(await client.GET("/v1/worlds", { params: { query: { limit: LIMIT } } })),
  });
}

export function useRunList() {
  return useQuery({
    queryKey: qk.runs,
    queryFn: async () =>
      bodyOf(await client.GET("/v1/runs", { params: { query: { limit: LIMIT } } })),
  });
}

export function useRun(runId: string, opts: { refetchInterval?: number | false } = {}) {
  return useQuery({
    queryKey: qk.run(runId),
    enabled: Boolean(runId),
    refetchInterval: opts.refetchInterval ?? false,
    queryFn: async () =>
      bodyOf(await client.GET("/v1/runs/{run_id}", { params: { path: { run_id: runId } } })),
  });
}

export function useRunEpisodes(runId: string, opts: { refetchInterval?: number | false } = {}) {
  return useQuery({
    queryKey: qk.runEpisodes(runId),
    enabled: Boolean(runId),
    refetchInterval: opts.refetchInterval ?? false,
    queryFn: async () =>
      bodyOf(
          await client.GET("/v1/runs/{run_id}/episodes", {
            params: { path: { run_id: runId }, query: { limit: LIMIT } },
          }),
        ),
  });
}

export function useRunReport(runId: string) {
  return useQuery({
    queryKey: qk.runReport(runId),
    queryFn: async () =>
      bodyOf(
          await client.GET("/v1/runs/{run_id}/report", { params: { path: { run_id: runId } } }),
        ),
  });
}

export function useEpisode(episodeId: string, opts: { refetchInterval?: number | false } = {}) {
  return useQuery({
    queryKey: qk.episode(episodeId),
    refetchInterval: opts.refetchInterval ?? false,
    queryFn: async () =>
      bodyOf(
          await client.GET("/v1/episodes/{episode_id}", {
            params: { path: { episode_id: episodeId }, query: {} },
          }),
        ),
  });
}

export function useModelCatalog() {
  return useQuery({
    queryKey: qk.modelCatalog,
    staleTime: Infinity,
    queryFn: async () => bodyOf(await client.GET("/v1/models/catalog")),
  });
}

export function useModelSettings() {
  return useQuery({
    queryKey: qk.modelSettings,
    queryFn: async () => bodyOf(await client.GET("/v1/settings/models")),
  });
}
