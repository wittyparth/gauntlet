"use client";

import { useQuery } from "@tanstack/react-query";

import { bodyOf, client } from "@/lib/api/client";

/** Public route: the committed study results, no sign-in. */
export function useBenchmarks() {
  return useQuery({
    queryKey: ["meta", "benchmarks"],
    staleTime: 300_000,
    queryFn: async () => bodyOf(await client.GET("/v1/meta/benchmarks")),
  });
}

export type Study = NonNullable<ReturnType<typeof useBenchmarks>["data"]>["studies"][number];
