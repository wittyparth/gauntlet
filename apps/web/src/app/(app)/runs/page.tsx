"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { RunTable } from "@/components/runs/run-table";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { FilterBar } from "@/components/shared/filter-bar";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { useRunList } from "@/lib/api/hooks/read";
import { isTerminalRun } from "@/lib/api/models";

const FACETS = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "finished", label: "Finished" },
];

function Runs() {
  const router = useRouter();
  const params = useSearchParams();
  const status = params.get("status") ?? "all";
  const q = useRunList();
  const all = q.data?.items ?? [];
  const runs = all.filter((r) => (status === "all" ? true : status === "active" ? !isTerminalRun(r.status) : isTerminalRun(r.status)));
  return (
    <>
      <PageHeader title="Runs" breadcrumbs={[{ label: "Runs" }]} meta={<span className="text-muted-foreground text-xs">{runs.length}</span>} />
      <div className="flex flex-col gap-3 p-4">
        <FilterBar
          facets={FACETS}
          facet={status}
          onFacetChange={(v) => router.replace(v === "all" ? "/runs" : `/runs?status=${v}`)}
        />
        {q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : (
          <RunTable
            runs={runs}
            isLoading={q.isLoading}
            emptyState={
              all.length === 0 ? (
                <EmptyState title="No runs yet" body="Start one from an agent." action={<Button render={<Link href="/agents" />}>Go to agents</Button>} />
              ) : (
                <EmptyState title="No runs match this filter" action={<Button variant="outline" onClick={() => router.replace("/runs")}>Clear filters</Button>} />
              )
            }
          />
        )}
      </div>
    </>
  );
}

export default function RunsPage() {
  return (
    <Suspense>
      <Runs />
    </Suspense>
  );
}
