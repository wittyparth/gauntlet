"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { bodyOf, client } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { qk, qkSec } from "@/lib/query-keys";

type Schemas = components["schemas"];
export type Finding = Schemas["FindingListOut"]["items"][number];
export type FindingDetail = Schemas["FindingDetailOut"];
export type FindingFilters = { status?: string; severity?: string; category?: string; agent_version_id?: string; q?: string };

/** Findings in this workspace. Filters are sent to the API; "all" or empty means none. */
export function useFindingList(filters: FindingFilters = {}) {
  const query = Object.fromEntries(Object.entries(filters).filter(([, v]) => v && v !== "all"));
  return useQuery({
    queryKey: qkSec.findings(query),
    queryFn: async () => {
      const res = bodyOf(await client.GET("/v1/findings", { params: { query: { ...query, limit: 200 } } }));
      return { ...res, items: res.items as Finding[] };
    },
  });
}

export function useFinding(findingId: string) {
  return useQuery({
    queryKey: qkSec.finding(findingId),
    queryFn: async () =>
      bodyOf(
        await client.GET("/v1/findings/{finding_id}", { params: { path: { finding_id: findingId } } }),
      ) as FindingDetail,
  });
}

/** Optimistic status change; rolls back on error (the server rejects illegal transitions). */
export function useUpdateFindingStatus(findingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { status: string; note?: string }) =>
      bodyOf(
        await client.PATCH("/v1/findings/{finding_id}", {
          params: { path: { finding_id: findingId } },
          body: { status: vars.status, note: vars.note ?? null },
        }),
      ),
    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey: qkSec.finding(findingId) });
      const prev = qc.getQueryData<FindingDetail>(qkSec.finding(findingId));
      if (prev) qc.setQueryData(qkSec.finding(findingId), { ...prev, status: vars.status });
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(qkSec.finding(findingId), ctx.prev);
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: qkSec.finding(findingId) });
      void qc.invalidateQueries({ queryKey: ["findings"] });
    },
  });
}

type RunVerb = "replay" | "verify";

/** Replay or verify create a run; the caller links to it. */
export function useFindingRun(findingId: string, verb: RunVerb) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const params = { params: { path: { finding_id: findingId } }, body: null };
      return verb === "replay"
        ? bodyOf(await client.POST("/v1/findings/{finding_id}/replay", params))
        : bodyOf(await client.POST("/v1/findings/{finding_id}/verify", params));
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.runs });
      void qc.invalidateQueries({ queryKey: qkSec.finding(findingId) });
    },
  });
}

export function usePinFinding(findingId: string) {
  return useMutation({
    mutationFn: async () =>
      bodyOf(await client.POST("/v1/findings/{finding_id}/pin", { params: { path: { finding_id: findingId } } })),
  });
}

export type ExportFormat = "md" | "json" | "sarif";

/** Fetch an export through the proxy and hand it to the browser as a download. */
export function useExportFinding(findingId: string) {
  return useMutation({
    mutationFn: async (format: ExportFormat) => {
      const res = await client.GET("/v1/findings/{finding_id}/export", {
        params: { path: { finding_id: findingId }, query: { format } },
        parseAs: "text",
      });
      const text = bodyOf(res);
      const mime = format === "md" ? "text/markdown" : "application/json";
      const url = URL.createObjectURL(new Blob([text], { type: mime }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `${findingId}.${format === "sarif" ? "sarif.json" : format}`;
      a.click();
      URL.revokeObjectURL(url);
      return format;
    },
  });
}
