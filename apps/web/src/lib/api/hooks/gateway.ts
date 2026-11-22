"use client";

import { useQuery } from "@tanstack/react-query";

import { bodyOf, client } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { qkG } from "@/lib/query-keys";

type Schemas = components["schemas"];
export type Decision = Schemas["DecisionRecord"];
export type GatewayStats = Schemas["StatsOut"];
export type DecisionFilters = { action?: string; tool?: string; policy_id?: string };

/** The API has no decision stream, so the console polls every 5 s while the tab is visible. */
export const DECISION_POLL_MS = 5000;

export function useGatewayDecisions(filters: DecisionFilters) {
  return useQuery({
    queryKey: qkG.decisions(filters),
    refetchInterval: DECISION_POLL_MS,
    refetchIntervalInBackground: false,
    queryFn: async () =>
      bodyOf(
        await client.GET("/v1/gateway/decisions", {
          params: { query: { limit: 100, action: filters.action || undefined, tool: filters.tool || undefined, policy_id: filters.policy_id || undefined } },
        }),
      ),
  });
}

export function useGatewayStats(window = "1h") {
  return useQuery({
    queryKey: qkG.stats(window),
    refetchInterval: DECISION_POLL_MS,
    queryFn: async () => bodyOf(await client.GET("/v1/gateway/stats", { params: { query: { window } } })),
  });
}
