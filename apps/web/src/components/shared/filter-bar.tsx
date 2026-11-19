"use client";

import type { ReactNode } from "react";

import { Search } from "@/components/animate-ui/icons/search";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

export type Facet = { value: string; label: string };

/** Single-select status facets plus a search box. State lives in the caller (URL query string). */
export function FilterBar({
  facets,
  facet,
  onFacetChange,
  search,
  onSearchChange,
  searchLabel = "Search",
  children,
}: {
  facets?: Facet[];
  facet?: string;
  onFacetChange?: (value: string) => void;
  search?: string;
  onSearchChange?: (value: string) => void;
  searchLabel?: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {facets && onFacetChange ? (
        <ToggleGroup
          value={facet ? [facet] : []}
          onValueChange={(v) => {
            const next = v[0];
            if (next) onFacetChange(next);
          }}
          variant="outline"
          size="sm"
          aria-label="Filter"
        >
          {facets.map((f) => (
            <ToggleGroupItem key={f.value} value={f.value}>
              {f.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      ) : null}
      {children}
      {onSearchChange ? (
        <div className="relative">
          <Search size={14} className="text-muted-foreground pointer-events-none absolute top-2 left-2" />
          <Input
            aria-label={searchLabel}
            placeholder={searchLabel}
            value={search ?? ""}
            onChange={(e) => onSearchChange(e.target.value)}
            className="h-8 w-56 pl-7"
          />
        </div>
      ) : null}
    </div>
  );
}
