"use client";

import { useQuery } from "@tanstack/react-query";

import { bodyOf, client } from "@/lib/api/client";
import {
  agentSchema,
  agentVersionSchema,
  episodeDetailSchema,
  episodeRowSchema,
  listOf,
  projectSchema,
  reportSchema,
  runSchema,
  scenarioRecordSchema,
  suiteSchema,
  worldSchema,
} from "@/lib/api/models";
import { qk } from "@/lib/query-keys";

const LIMIT = 200;

export function useProjectList() {
  return useQuery({
    queryKey: qk.projects,
    queryFn: async () =>
      listOf(projectSchema).parse(bodyOf(await client.GET("/v1/projects", { params: { query: {} } }))),
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
      listOf(agentSchema).parse(
        bodyOf(await client.GET("/v1/agents", { params: { query: { limit: LIMIT } } })),
      ),
  });
}

export function useAgent(agentId: string) {
  return useQuery({
    queryKey: qk.agent(agentId),
    queryFn: async () =>
      agentSchema.parse(
        bodyOf(await client.GET("/v1/agents/{agent_id}", { params: { path: { agent_id: agentId } } })),
      ),
  });
}

export function useAgentVersions(agentId: string) {
  return useQuery({
    queryKey: qk.agentVersions(agentId),
    queryFn: async () =>
      listOf(agentVersionSchema).parse(
        bodyOf(
          await client.GET("/v1/agents/{agent_id}/versions", {
            params: { path: { agent_id: agentId }, query: { limit: LIMIT } },
          }),
        ),
      ),
  });
}

export function useScenarioList() {
  return useQuery({
    queryKey: qk.scenarios,
    queryFn: async () =>
      listOf(scenarioRecordSchema).parse(
        bodyOf(await client.GET("/v1/scenarios", { params: { query: { limit: LIMIT } } })),
      ),
  });
}

export function useScenario(scenarioId: string) {
  return useQuery({
    queryKey: qk.scenario(scenarioId),
    queryFn: async () =>
      scenarioRecordSchema.parse(
        bodyOf(
          await client.GET("/v1/scenarios/{scenario_id}", {
            params: { path: { scenario_id: scenarioId } },
          }),
        ),
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
      listOf(suiteSchema).parse(
        bodyOf(await client.GET("/v1/suites", { params: { query: { limit: LIMIT } } })),
      ),
  });
}

export function useWorld(worldId: string | null | undefined) {
  return useQuery({
    queryKey: qk.world(worldId ?? ""),
    enabled: Boolean(worldId),
    queryFn: async () =>
      worldSchema.parse(
        bodyOf(
          await client.GET("/v1/worlds/{doc_id}", {
            params: { path: { doc_id: worldId ?? "" }, query: {} },
          }),
        ),
      ),
  });
}

export function useWorldList() {
  return useQuery({
    queryKey: qk.worlds,
    queryFn: async () =>
      listOf(worldSchema).parse(
        bodyOf(await client.GET("/v1/worlds", { params: { query: { limit: LIMIT } } })),
      ),
  });
}

export function useRunList() {
  return useQuery({
    queryKey: qk.runs,
    queryFn: async () =>
      listOf(runSchema).parse(
        bodyOf(await client.GET("/v1/runs", { params: { query: { limit: LIMIT } } })),
      ),
  });
}

export function useRun(runId: string, opts: { refetchInterval?: number | false } = {}) {
  return useQuery({
    queryKey: qk.run(runId),
    enabled: Boolean(runId),
    refetchInterval: opts.refetchInterval ?? false,
    queryFn: async () =>
      runSchema.parse(
        bodyOf(await client.GET("/v1/runs/{run_id}", { params: { path: { run_id: runId } } })),
      ),
  });
}

export function useRunEpisodes(runId: string, opts: { refetchInterval?: number | false } = {}) {
  return useQuery({
    queryKey: qk.runEpisodes(runId),
    enabled: Boolean(runId),
    refetchInterval: opts.refetchInterval ?? false,
    queryFn: async () =>
      listOf(episodeRowSchema).parse(
        bodyOf(
          await client.GET("/v1/runs/{run_id}/episodes", {
            params: { path: { run_id: runId }, query: { limit: LIMIT } },
          }),
        ),
      ),
  });
}

export function useRunReport(runId: string) {
  return useQuery({
    queryKey: qk.runReport(runId),
    queryFn: async () =>
      reportSchema.parse(
        bodyOf(
          await client.GET("/v1/runs/{run_id}/report", { params: { path: { run_id: runId } } }),
        ),
      ),
  });
}

export function useEpisode(episodeId: string, opts: { refetchInterval?: number | false } = {}) {
  return useQuery({
    queryKey: qk.episode(episodeId),
    refetchInterval: opts.refetchInterval ?? false,
    queryFn: async () =>
      episodeDetailSchema.parse(
        bodyOf(
          await client.GET("/v1/episodes/{episode_id}", {
            params: { path: { episode_id: episodeId }, query: {} },
          }),
        ),
      ),
  });
}
