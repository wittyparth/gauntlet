"use client";

import { PolicyTable } from "@/components/gateway/policy-table";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { PageHeader } from "@/components/shared/page-header";
import { usePolicyList } from "@/lib/api/hooks/policies";

export default function PoliciesPage() {
  const q = usePolicyList();
  return (
    <>
      <PageHeader title="Policies" breadcrumbs={[{ label: "Gateway", href: "/gateway" }, { label: "Policies" }]} />
      <div className="flex flex-col gap-3 p-4">
        {q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : q.data && q.data.length === 0 ? (
          <EmptyState title="No policy yet" body="Create a policy from your written rules, or start from a finding's suggested rule." />
        ) : (
          <PolicyTable policies={q.data ?? []} isLoading={q.isLoading} />
        )}
      </div>
    </>
  );
}
