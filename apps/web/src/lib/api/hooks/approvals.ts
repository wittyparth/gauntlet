"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { bodyOf, client } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { qkG } from "@/lib/query-keys";

export type Approval = components["schemas"]["ApprovalOut"];

export function useApprovals(status: "pending" | "approved" | "denied" | "expired" = "pending") {
  return useQuery({
    queryKey: qkG.approvals(status),
    refetchInterval: 5000,
    queryFn: async () => bodyOf(await client.GET("/v1/gateway/approvals", { params: { query: { status, limit: 100 } } })),
  });
}

export function useDecideApproval() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { id: string; decision: "approve" | "deny"; note?: string }) =>
      bodyOf(
        await client.POST("/v1/gateway/approvals/{approval_id}/decide", {
          params: { path: { approval_id: v.id } },
          body: { decision: v.decision, note: v.note?.trim() || null },
        }),
      ),
    onSettled: () => qc.invalidateQueries({ queryKey: ["gateway", "approvals"] }),
  });
}
