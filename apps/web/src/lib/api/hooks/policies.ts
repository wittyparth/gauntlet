"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { bodyOf, client } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { qkG } from "@/lib/query-keys";

type Schemas = components["schemas"];
export type PolicyOut = Schemas["PolicyOut"];
export type PolicyRule = Schemas["PolicyRule"];
export type Proposal = Schemas["Proposal"];
export type CompiledPolicy = Schemas["CompiledPolicy"];
export type PolicyTest = Schemas["PolicyTestOut"];

/** The stored `result` of a finished policy test (gauntlet_core.policy.PolicyTestReport). */
export type PolicyTestReport = {
  attacks: number;
  benign: number;
  skipped: number;
  blocked: number;
  broken: number;
  block_rate: number;
  fp_rate: number;
  per_rule: { rule_id: string; blocked: number; false_positives: number }[];
  tradeoff: { rules: string[]; added: string; blocked: number; false_positives: number; block_rate: number; fp_rate: number }[];
  outcomes: { episode_id: string; kind: "attack" | "benign"; first_block_seq: number | null; rule_id: string | null; objective_seq: number | null; effective: boolean }[];
};
export const reportOf = (t: PolicyTest | undefined | null) => (t?.status === "done" && t.result ? (t.result as unknown as PolicyTestReport) : null);

export function usePolicyList() {
  return useQuery({ queryKey: qkG.policies, queryFn: async () => bodyOf(await client.GET("/v1/policies")) });
}

export function usePolicy(policyId: string) {
  return useQuery({
    queryKey: qkG.policy(policyId),
    queryFn: async () => bodyOf(await client.GET("/v1/policies/{policy_id}", { params: { path: { policy_id: policyId }, query: {} } })),
  });
}

export function useProposals(policyId: string) {
  return useQuery({
    queryKey: qkG.proposals(policyId),
    queryFn: async () =>
      bodyOf(await client.GET("/v1/policies/{policy_id}/proposals", { params: { path: { policy_id: policyId }, query: {} } })),
  });
}

function useInvalidatePolicy(policyId: string) {
  const qc = useQueryClient();
  return () => Promise.all([qc.invalidateQueries({ queryKey: qkG.policy(policyId) }), qc.invalidateQueries({ queryKey: qkG.policies })]);
}

/** Saving a rule edits the draft's proposal; publishing is what creates the next version. */
export function useSaveRule(policyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { clauseId: string; status: "proposed" | "accepted" | "rejected" | "edited"; rule?: PolicyRule | null }) =>
      bodyOf(
        await client.PATCH("/v1/policies/{policy_id}/proposals/{clause_id}", {
          params: { path: { policy_id: policyId, clause_id: v.clauseId } },
          body: { status: v.status, rule: (v.rule ?? null) as never },
        }),
      ),
    onSuccess: (data) => qc.setQueryData(qkG.proposals(policyId), data),
  });
}

export function usePublishPolicy(policyId: string) {
  const done = useInvalidatePolicy(policyId);
  return useMutation({
    mutationFn: async (body: { mode: "shadow" | "enforce"; fail: "open" | "closed" }) =>
      bodyOf(await client.POST("/v1/policies/{policy_id}/publish", { params: { path: { policy_id: policyId } }, body })),
    onSuccess: done,
  });
}

export function useEnforcePolicy(policyId: string) {
  const done = useInvalidatePolicy(policyId);
  return useMutation({
    mutationFn: async (override: boolean) =>
      bodyOf(await client.POST("/v1/policies/{policy_id}/enforce", { params: { path: { policy_id: policyId } }, body: { override } })),
    onSuccess: done,
  });
}

export function usePolicyTests(policyId: string) {
  return useQuery({
    queryKey: qkG.tests(policyId),
    refetchInterval: (q) => (q.state.data?.some((t) => t.status === "queued" || t.status === "running") ? 2000 : false),
    queryFn: async () => bodyOf(await client.GET("/v1/policies/{policy_id}/tests", { params: { path: { policy_id: policyId } } })),
  });
}

export function useRunPolicyTest(policyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (agentVersionId: string) =>
      bodyOf(
        await client.POST("/v1/policies/{policy_id}/test", {
          params: { path: { policy_id: policyId } },
          body: { agent_version_id: agentVersionId, attack_runs: null, benign_runs: null, max_benign: 200 },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: qkG.tests(policyId) }),
  });
}
