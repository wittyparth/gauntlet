"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";

import { ScenarioTable } from "@/components/scenarios/scenario-table";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { FilterBar } from "@/components/shared/filter-bar";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useScenarioList } from "@/lib/api/hooks/read";

const FACETS = [
  { value: "all", label: "All" },
  { value: "approved", label: "Approved" },
  { value: "draft", label: "Draft" },
];
const ALL = "__all";

function Scenarios() {
  const router = useRouter();
  const params = useSearchParams();
  const status = params.get("status") ?? "all";
  const source = params.get("source") ?? ALL;
  const tag = params.get("tag") ?? ALL;
  const search = params.get("q") ?? "";
  const q = useScenarioList();
  const all = useMemo(() => q.data?.items ?? [], [q.data]);

  const set = (key: string, value: string | null) => {
    const next = new URLSearchParams(params.toString());
    if (!value || value === ALL || value === "all") next.delete(key);
    else next.set(key, value);
    const qs = next.toString();
    router.replace(qs ? `/scenarios?${qs}` : "/scenarios", { scroll: false });
  };

  const sources = useMemo(() => [...new Set(all.map((r) => r.source))].sort(), [all]);
  const tags = useMemo(
    () => [...new Set(all.flatMap((r) => Object.entries(r.scenario.tags).map(([k, v]) => `${k}:${v}`)))].sort(),
    [all],
  );
  const rows = all.filter((r) => {
    if (status !== "all" && r.status !== status) return false;
    if (source !== ALL && r.source !== source) return false;
    if (tag !== ALL && !Object.entries(r.scenario.tags).some(([k, v]) => `${k}:${v}` === tag)) return false;
    const needle = search.toLowerCase();
    return !needle || r.scenario.title.toLowerCase().includes(needle) || r.scenario.goal.toLowerCase().includes(needle);
  });
  const filtered = status !== "all" || source !== ALL || tag !== ALL || search !== "";

  return (
    <>
      <PageHeader
        title="Scenarios"
        breadcrumbs={[{ label: "Scenarios" }]}
        meta={<span className="text-muted-foreground font-mono text-xs" aria-label="Scenario count">{rows.length}</span>}
      />
      <div className="flex flex-col gap-3 p-4">
        <FilterBar
          facets={FACETS}
          facet={status}
          onFacetChange={(v) => set("status", v)}
          search={search}
          onSearchChange={(v) => set("q", v)}
          searchLabel="Search title or goal"
        >
          <Select items={[{ value: ALL, label: "All sources" }, ...sources.map((s) => ({ value: s, label: s }))]} value={source} onValueChange={(v) => set("source", v)}>
            <SelectTrigger size="sm" aria-label="Source" className="w-32"><SelectValue placeholder="Source" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All sources</SelectItem>
              {sources.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select items={[{ value: ALL, label: "All tags" }, ...tags.map((t) => ({ value: t, label: t }))]} value={tag} onValueChange={(v) => set("tag", v)}>
            <SelectTrigger size="sm" aria-label="Tag" className="w-44"><SelectValue placeholder="Tag" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All tags</SelectItem>
              {tags.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
            </SelectContent>
          </Select>
        </FilterBar>
        {q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : (
          <ScenarioTable
            rows={rows}
            isLoading={q.isLoading}
            emptyState={
              filtered ? (
                <EmptyState title="No scenarios match these filters" action={<Button variant="outline" onClick={() => router.replace("/scenarios")}>Clear filters</Button>} />
              ) : (
                <EmptyState title="No scenarios yet" body="Generate a starter suite from an agent, or load a scenario pack." />
              )
            }
          />
        )}
      </div>
    </>
  );
}

export default function ScenariosPage() {
  return (
    <Suspense>
      <Scenarios />
    </Suspense>
  );
}
