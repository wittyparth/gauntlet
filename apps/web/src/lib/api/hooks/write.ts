"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ApiError, bodyOf, client } from "@/lib/api/client";
import { isDryRun } from "@/lib/api/models";
import type { components } from "@/lib/api/schema";
import { qk } from "@/lib/query-keys";

type Schemas = components["schemas"];

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["ProjectIn"]) =>
      bodyOf(await client.POST("/v1/projects", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.projects }),
  });
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["AgentIn"]) =>
      bodyOf(await client.POST("/v1/agents", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.agents }),
  });
}

export function useCreateAgentVersion(agentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["VersionIn"]) =>
      bodyOf(
          await client.POST("/v1/agents/{agent_id}/versions", {
            params: { path: { agent_id: agentId } },
            body,
          }),
        ),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.agent(agentId) }),
  });
}

export function useCreateSuite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["Suite"]) =>
      bodyOf(await client.POST("/v1/suites", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.suites }),
  });
}

export function useRunEstimate() {
  return useMutation({
    mutationFn: async (body: Schemas["RunCreate"]) => {
      const res = bodyOf(await client.POST("/v1/runs", { params: { query: { dry_run: true } }, body }));
      if (!isDryRun(res)) throw new ApiError(500, "unexpected", "Expected a dry-run answer.");
      return res;
    },
  });
}

export function useCreateRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["RunCreate"]) => {
      const res = bodyOf(await client.POST("/v1/runs", { body }));
      if (isDryRun(res)) throw new ApiError(500, "unexpected", "Expected a created run.");
      return res;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.runs }),
  });
}

type RunVerb = "cancel" | "pause" | "resume";

function useRunVerb(runId: string, verb: RunVerb) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const params = { params: { path: { run_id: runId } } };
      if (verb === "cancel") return bodyOf(await client.POST("/v1/runs/{run_id}/cancel", params));
      if (verb === "pause") return bodyOf(await client.POST("/v1/runs/{run_id}/pause", params));
      return bodyOf(await client.POST("/v1/runs/{run_id}/resume", params));
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.run(runId) }),
  });
}

export const useCancelRun = (runId: string) => useRunVerb(runId, "cancel");
export const usePauseRun = (runId: string) => useRunVerb(runId, "pause");
export const useResumeRun = (runId: string) => useRunVerb(runId, "resume");

export function useGenerateScenarios(agentId: string) {
  return useMutation({
    mutationFn: async () =>
      bodyOf(
        await client.POST("/v1/agents/{agent_id}/generate-scenarios", {
          params: { path: { agent_id: agentId } },
        }),
      ),
  });
}
