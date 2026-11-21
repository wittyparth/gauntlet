"use client";

import { useQuery } from "@tanstack/react-query";

import { bodyOf, client } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { qkSec } from "@/lib/query-keys";

export type Attack = components["schemas"]["Attack"];
export type AttackFilters = { vector?: string; source?: string; q?: string };

/** Library attacks matching the server-side filters; follows the cursor up to a safe cap. */
export function useAttackList(filters: AttackFilters = {}) {
  const query = Object.fromEntries(Object.entries(filters).filter(([, v]) => v && v !== "all"));
  return useQuery({
    queryKey: qkSec.attacks(query),
    queryFn: async () => {
      const items: Attack[] = [];
      let cursor: string | null | undefined;
      for (let page = 0; page < 10; page++) {
        const res = bodyOf(
          await client.GET("/v1/attacks", { params: { query: { ...query, limit: 200, cursor: cursor ?? undefined } } }),
        );
        items.push(...res.items);
        cursor = res.next_cursor;
        if (!cursor) break;
      }
      return items;
    },
  });
}

export function useTaxonomy() {
  return useQuery({
    queryKey: qkSec.taxonomy,
    staleTime: Infinity,
    queryFn: async () => bodyOf(await client.GET("/v1/security/taxonomy")),
  });
}
