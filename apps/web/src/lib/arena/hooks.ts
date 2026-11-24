"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { components } from "./schema";
import { arena, arenaBody } from "./client";

type S = components["schemas"];
export type ArenaLevels = S["LevelsOut"];
export type ArenaLevel = S["LevelOut"];
export type Attempt = S["AttemptOut"];
export type Turn = S["TurnOut"];
export type LeaderRow = S["LeaderRow"];

export const qkArena = {
  levels: ["arena", "levels"] as const,
  leaderboard: (level: number | null) => ["arena", "leaderboard", level] as const,
};

export function useArenaLevels() {
  return useQuery({
    queryKey: qkArena.levels,
    refetchInterval: 30_000,
    queryFn: async () => arenaBody(await arena.GET("/arena/v1/levels")),
  });
}

export function useLeaderboard(level: number | null) {
  return useQuery({
    queryKey: qkArena.leaderboard(level),
    refetchInterval: 15_000,
    queryFn: async () =>
      arenaBody(await arena.GET("/arena/v1/leaderboard", { params: { query: level ? { level } : {} } })),
  });
}

export function useCreateHandle() {
  return useMutation({
    mutationFn: async (handle: string) => arenaBody(await arena.POST("/arena/v1/handles", { body: { handle } })),
  });
}

export function useStartAttempt() {
  return useMutation({
    mutationFn: async (v: { handle: string; level: number }) =>
      arenaBody(await arena.POST("/arena/v1/attempts", { body: v })),
  });
}

export function useSendMessage(attemptId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (text: string) => {
      if (!attemptId) throw new Error("no attempt");
      return arenaBody(
        await arena.POST("/arena/v1/attempts/{attempt_id}/messages", {
          params: { path: { attempt_id: attemptId } },
          body: { text },
        }),
      );
    },
    onSuccess: (t) => {
      if (t.solved) void qc.invalidateQueries({ queryKey: ["arena", "leaderboard"] });
    },
  });
}

export function useReportAttempt() {
  return useMutation({
    mutationFn: async (attemptId: string) =>
      arenaBody(await arena.POST("/arena/v1/attempts/{attempt_id}/report", { params: { path: { attempt_id: attemptId } } })),
  });
}
