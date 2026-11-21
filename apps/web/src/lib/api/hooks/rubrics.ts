"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { bodyOf, client } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { qk, qkQ } from "@/lib/query-keys";

type Schemas = components["schemas"];
export type RubricDoc = Schemas["RubricDoc"];
export type Calibration = Schemas["CalibrationOut"];

export function useRubricList() {
  return useQuery({
    queryKey: qkQ.rubrics,
    queryFn: async () => bodyOf(await client.GET("/v1/rubrics", { params: { query: { limit: 200 } } })),
  });
}

export function useRubric(rubricId: string) {
  return useQuery({
    queryKey: qkQ.rubric(rubricId),
    enabled: Boolean(rubricId),
    queryFn: async () =>
      bodyOf(await client.GET("/v1/rubrics/{doc_id}", { params: { path: { doc_id: rubricId } } })),
  });
}

export function useCalibrations(rubricId: string) {
  return useQuery({
    queryKey: qkQ.calibrations(rubricId),
    enabled: Boolean(rubricId),
    queryFn: async () =>
      bodyOf(
        await client.GET("/v1/rubrics/{rubric_id}/calibrations", { params: { path: { rubric_id: rubricId } } }),
      ),
  });
}

export function useRejudgeEpisode(episodeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      bodyOf(
        await client.POST("/v1/episodes/{episode_id}/rejudge", {
          params: { path: { episode_id: episodeId } },
          body: { rubrics: null, force: false },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.episode(episodeId) }),
  });
}
