"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { bodyOf, client } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { qk, qkQ } from "@/lib/query-keys";

type Schemas = components["schemas"];
export type QueueItem = Schemas["QueueItem"];
export type ReviewItem = Schemas["ItemOut"];
export type LabelResult = "pass" | "fail" | "na";

export function useReviewQueue(rubric: string) {
  return useQuery({
    queryKey: qkQ.reviewQueue(rubric),
    enabled: Boolean(rubric),
    queryFn: async () =>
      bodyOf(await client.GET("/v1/review/queue", { params: { query: { rubric, limit: 40 } } })),
  });
}

/** `reveal` asks the server for the judge's prediction; it stays off until the labeller asks. */
export function useReviewItem(episodeId: string | null, rubric: string, reveal: boolean) {
  return useQuery({
    queryKey: qkQ.reviewItem(episodeId ?? "", rubric, reveal),
    enabled: Boolean(episodeId && rubric),
    queryFn: async () =>
      bodyOf(
        await client.GET("/v1/review/items/{episode_id}/{rubric_id}", {
          params: { path: { episode_id: episodeId ?? "", rubric_id: rubric }, query: { reveal } },
        }),
      ),
  });
}

export function useSubmitLabel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { episode_id: string; rubric_id: string; result: LabelResult }) =>
      bodyOf(await client.POST("/v1/review/labels", { body })),
    onSuccess: (_d, v) => {
      void qc.invalidateQueries({ queryKey: qk.episode(v.episode_id) });
      void qc.invalidateQueries({ queryKey: ["rubrics", v.rubric_id, "calibrations"] });
    },
  });
}
