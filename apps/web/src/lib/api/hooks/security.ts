"use client";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, bodyOf, client } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { qk, qkSec } from "@/lib/query-keys";

type Schemas = components["schemas"];
export type Posture = Schemas["PostureOut"];
export type CoverageCell = Schemas["CoverageCell"];
export type KillState = Schemas["KillState"];
export type Verification = Schemas["VerificationOut"];
export type AuditRow = Schemas["AuditRow"];

export function usePosture(agentId: string, versionId: string) {
  return useQuery({
    queryKey: qkSec.posture(agentId, versionId),
    enabled: Boolean(agentId && versionId),
    queryFn: async () => {
      const res = bodyOf(
        await client.GET("/v1/agents/{agent_id}/versions/{version_id}/posture", {
          params: { path: { agent_id: agentId, version_id: versionId }, query: { format: "json" } },
        }),
      );
      // `format=md` answers with a string; the JSON format is the only one this screen asks for.
      if (typeof res === "string") throw new ApiError(500, "unexpected", "Expected the JSON posture report.");
      return res as Posture;
    },
  });
}

export function useCoverage(agentId: string, versionId: string) {
  return useQuery({
    queryKey: qkSec.coverage(agentId, versionId),
    enabled: Boolean(agentId && versionId),
    queryFn: async () =>
      bodyOf(
        await client.GET("/v1/agents/{agent_id}/versions/{version_id}/coverage", {
          params: { path: { agent_id: agentId, version_id: versionId } },
        }),
      ),
  });
}

export function useKillSwitch() {
  return useQuery({
    queryKey: qkSec.killswitch,
    refetchInterval: 15_000,
    queryFn: async () => bodyOf(await client.GET("/v1/killswitch")),
  });
}

export function useEngageKillSwitch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (reason: string) =>
      bodyOf(await client.POST("/v1/killswitch", { body: { scope: "workspace", run_id: null, reason } })),
    onSuccess: (data) => qc.setQueryData(qkSec.killswitch, data),
  });
}

export function useReleaseKillSwitch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      bodyOf(await client.DELETE("/v1/killswitch", { params: { query: { scope: "workspace" } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: qkSec.killswitch }),
  });
}

export function useVerifications() {
  return useQuery({
    queryKey: qkSec.verifications,
    queryFn: async () => bodyOf(await client.GET("/v1/targets/verifications")),
  });
}

export function useAttackScope() {
  return useQuery({
    queryKey: qkSec.attackScope,
    queryFn: async () => bodyOf(await client.GET("/v1/settings/attack-scope")),
  });
}

export function useAuditLog(filters: { action?: string; subject_type?: string } = {}) {
  const query = Object.fromEntries(Object.entries(filters).filter(([, v]) => v && v !== "all"));
  return useQuery({
    queryKey: qkSec.audit(query),
    queryFn: async () => bodyOf(await client.GET("/v1/audit", { params: { query: { ...query, limit: 200 } } })),
  });
}

export function useAuditChain() {
  return useQuery({
    queryKey: qkSec.auditVerify,
    queryFn: async () => bodyOf(await client.GET("/v1/audit/verify")),
  });
}

export function useCreateCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["CampaignCreate"]) => bodyOf(await client.POST("/v1/campaigns", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.runs }),
  });
}

/** Every agent version with its agent name, for pickers (one versions query per agent). */
export function useAllVersions() {
  const agents = useQuery({
    queryKey: qk.agents,
    queryFn: async () => bodyOf(await client.GET("/v1/agents", { params: { query: { limit: 200 } } })),
  });
  const list = agents.data?.items ?? [];
  const versions = useQueries({
    queries: list.map((a) => ({
      queryKey: qk.agentVersions(a.id),
      queryFn: async () =>
        bodyOf(
          await client.GET("/v1/agents/{agent_id}/versions", {
            params: { path: { agent_id: a.id }, query: { limit: 200 } },
          }),
        ),
    })),
  });
  const items = list.flatMap((a, i) =>
    (versions[i]?.data?.items ?? []).map((v) => ({ agentId: a.id, agentName: a.name, version: v })),
  );
  return {
    items,
    isLoading: agents.isLoading || versions.some((v) => v.isLoading),
    error: agents.error ?? versions.find((v) => v.error)?.error ?? null,
    refetch: () => void agents.refetch(),
  };
}
