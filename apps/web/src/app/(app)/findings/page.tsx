"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";

import { FindingTable } from "@/components/findings/finding-table";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { FilterBar } from "@/components/shared/filter-bar";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useFindingList } from "@/lib/api/hooks/findings";
import { useTaxonomy } from "@/lib/api/hooks/attacks";
import { useAllVersions } from "@/lib/api/hooks/security";

const FACETS = [
  { value: "open", label: "Open" },
  { value: "triaged", label: "Triaged" },
  { value: "in_progress", label: "In progress" },
  { value: "fixed", label: "Fixed" },
  { value: "all", label: "All" },
];
const SEVERITIES = ["critical", "high", "medium", "low"];

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  const items = [{ value: "all", label }, ...options];
  return (
    <Select items={items} value={value} onValueChange={(v) => v && onChange(v)}>
      <SelectTrigger size="sm" aria-label={label} className="w-40">
        <SelectValue placeholder={label} />
      </SelectTrigger>
      <SelectContent>
        {items.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function Inbox() {
  const router = useRouter();
  const params = useSearchParams();
  const status = params.get("status") ?? "open";
  const severity = params.get("severity") ?? "all";
  const category = params.get("category") ?? "all";
  const agent = params.get("agent") ?? "all";
  const search = params.get("q") ?? "";

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (!value || value === "all" || (key === "status" && value === "open")) next.delete(key);
    else next.set(key, value);
    const qs = next.toString();
    router.replace(qs ? `/findings?${qs}` : "/findings", { scroll: false });
  };

  const q = useFindingList({ status, severity, category, agent_version_id: agent, q: search });
  const anyFilter = status !== "open" || severity !== "all" || category !== "all" || agent !== "all" || search !== "";
  const versions = useAllVersions();
  const taxonomy = useTaxonomy();
  const labels = useMemo(
    () => new Map(versions.items.map((v) => [v.version.id, `${v.agentName} ${v.version.label}`])),
    [versions.items],
  );
  const rows = q.data?.items ?? [];

  return (
    <>
      <PageHeader
        title="Findings"
        breadcrumbs={[{ label: "Findings" }]}
        meta={<span className="text-muted-foreground text-xs">{rows.length}</span>}
        actions={
          <Button size="sm" variant="outline" render={<Link href="/security/campaigns/new" />}>
            Launch campaign
          </Button>
        }
      />
      <div className="flex flex-col gap-3 p-4">
        <FilterBar
          facets={FACETS}
          facet={status}
          onFacetChange={(v) => setParam("status", v)}
          search={search}
          onSearchChange={(v) => setParam("q", v)}
          searchLabel="Search findings"
        >
          <FilterSelect label="Severity" value={severity} options={SEVERITIES.map((s) => ({ value: s, label: s }))} onChange={(v) => setParam("severity", v)} />
          <FilterSelect
            label="Category"
            value={category}
            options={(taxonomy.data?.categories ?? []).map((c) => ({ value: c.id, label: c.title }))}
            onChange={(v) => setParam("category", v)}
          />
          <FilterSelect
            label="Agent version"
            value={agent}
            options={versions.items.map((v) => ({ value: v.version.id, label: `${v.agentName} ${v.version.label}` }))}
            onChange={(v) => setParam("agent", v)}
          />
        </FilterBar>
        {q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : (
          <FindingTable
            findings={rows}
            versionLabels={labels}
            isLoading={q.isLoading}
            emptyState={
              anyFilter ? (
                <EmptyState
                  title="No findings match these filters"
                  action={
                    <Button variant="outline" onClick={() => router.replace("/findings")}>
                      Clear filters
                    </Button>
                  }
                />
              ) : (
                <EmptyState
                  title="No findings. Launch a campaign to look for some."
                  body="A campaign runs attacks against an agent version. Anything that succeeds lands here for triage."
                  action={<Button render={<Link href="/security/campaigns/new" />}>Launch a campaign</Button>}
                />
              )
            }
          />
        )}
      </div>
    </>
  );
}

export default function FindingsPage() {
  return (
    <Suspense>
      <Inbox />
    </Suspense>
  );
}
