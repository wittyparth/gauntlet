"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import type { Attack } from "@/lib/api/hooks/attacks";
import type { components } from "@/lib/api/schema";

import { sourceFamily, type LibraryFilters } from "./campaign-schema";

type Category = components["schemas"]["CategoryOut"];

const VECTORS = ["user_turn", "document", "tool_result", "tool_description", "system_context"];

/** Attack categories plus library filters (vector, source, text). Counts come from the library itself. */
export function CampaignAttackFields({
  categories,
  library,
  filters,
  onChange,
  loading,
  error,
}: {
  categories: Category[];
  library: Attack[];
  filters: LibraryFilters;
  onChange: (next: LibraryFilters) => void;
  loading: boolean;
  error?: string;
}) {
  const counts = new Map<string, number>();
  for (const a of library) counts.set(a.category, (counts.get(a.category) ?? 0) + 1);
  const offered = categories.filter((c) => !c.dangerous && (counts.get(c.id) ?? 0) > 0);
  const sources = [...new Set(library.map((a) => sourceFamily(a.source)))].sort();
  const toggle = (id: string, on: boolean) =>
    onChange({
      ...filters,
      categories: on ? [...filters.categories, id] : filters.categories.filter((c) => c !== id),
    });

  return (
    <div className="flex flex-col gap-4">
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 flex w-full items-center justify-between text-sm font-medium">
          Attack categories
          <span className="flex gap-2 text-xs font-normal">
            <button type="button" className="text-muted-foreground hover:text-foreground underline" onClick={() => onChange({ ...filters, categories: offered.map((c) => c.id) })}>
              Select all
            </button>
            <button type="button" className="text-muted-foreground hover:text-foreground underline" onClick={() => onChange({ ...filters, categories: [] })}>
              Clear
            </button>
          </span>
        </legend>
        {loading ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <ul className="grid gap-1.5 sm:grid-cols-2" data-testid="category-list">
            {offered.map((c) => (
              <li key={c.id} className="flex items-center gap-2">
                <Checkbox
                  id={`cat-${c.id}`}
                  checked={filters.categories.includes(c.id)}
                  onCheckedChange={(v) => toggle(c.id, v === true)}
                />
                <Label htmlFor={`cat-${c.id}`} className="flex flex-1 justify-between gap-2 font-normal">
                  <span>{c.title}</span>
                  <span className="text-muted-foreground font-mono text-xs tabular-nums">{counts.get(c.id)}</span>
                </Label>
              </li>
            ))}
          </ul>
        )}
        {error ? (
          <p role="alert" className="text-destructive text-xs">
            {error}
          </p>
        ) : null}
      </fieldset>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="lib-vector">Vector</Label>
          <Select
            items={[{ value: "all", label: "Any vector" }, ...VECTORS.map((v) => ({ value: v, label: v }))]}
            value={filters.vector}
            onValueChange={(v) => v && onChange({ ...filters, vector: v })}
          >
            <SelectTrigger id="lib-vector" aria-label="Vector" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Any vector</SelectItem>
              {VECTORS.map((v) => (
                <SelectItem key={v} value={v}>
                  {v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="lib-source">Library</Label>
          <Select
            items={[{ value: "all", label: "Any source" }, ...sources.map((s) => ({ value: s, label: s }))]}
            value={filters.source}
            onValueChange={(v) => v && onChange({ ...filters, source: v })}
          >
            <SelectTrigger id="lib-source" aria-label="Library source" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Any source</SelectItem>
              {sources.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="lib-q">Search attacks</Label>
          <Input id="lib-q" value={filters.q} onChange={(e) => onChange({ ...filters, q: e.target.value })} placeholder="title or technique" />
        </div>
      </div>
    </div>
  );
}
