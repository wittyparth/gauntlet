"use client";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { PageHeader } from "@/components/shared/page-header";
import { RubricTable } from "@/components/rubrics/rubric-table";
import { useRubricList } from "@/lib/api/hooks/rubrics";

export default function RubricsPage() {
  const q = useRubricList();
  return (
    <>
      <PageHeader title="Rubrics" breadcrumbs={[{ label: "Quality" }, { label: "Rubrics" }]} />
      <div className="flex flex-col gap-3 p-4">
        {q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : q.data && q.data.items.length === 0 ? (
          <EmptyState title="No rubrics" body="Rubrics describe what a judge asks of a trajectory." />
        ) : (
          <RubricTable rubrics={q.data?.items ?? []} isLoading={q.isLoading} />
        )}
      </div>
    </>
  );
}
