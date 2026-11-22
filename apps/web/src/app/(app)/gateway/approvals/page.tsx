"use client";

import { ApprovalCard } from "@/components/gateway/approval-card";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingCard } from "@/components/shared/loading";
import { PageHeader } from "@/components/shared/page-header";
import { useToast } from "@/components/shared/use-toast";
import { toApiError } from "@/lib/api/errors";
import { useApprovals, useDecideApproval } from "@/lib/api/hooks/approvals";

export default function ApprovalsPage() {
  const q = useApprovals("pending");
  const decide = useDecideApproval();
  const toast = useToast();
  const items = q.data ?? [];

  function onDecide(id: string, decision: "approve" | "deny", note?: string) {
    decide.mutate(
      { id, decision, note },
      {
        onSuccess: () => toast.success(decision === "approve" ? "Approved" : "Denied"),
        onError: (e) => {
          // Expired, or decided by someone else: the card leaves the list (the list refetches).
          const err = toApiError(e);
          if (err.status === 409) toast.error(e, "Already decided or expired");
          else toast.error(e, "Could not record the decision");
        },
      },
    );
  }
  return (
    <>
      <PageHeader title="Approvals" breadcrumbs={[{ label: "Gateway", href: "/gateway" }, { label: "Approvals" }]} meta={<span className="text-muted-foreground text-xs">{items.length} pending</span>} />
      <div className="flex flex-col gap-3 p-4">
        {q.isLoading ? <LoadingCard lines={4} /> : null}
        {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : null}
        {q.data && items.length === 0 ? <EmptyState title="Nothing waiting" body="Actions that a rule holds for a human appear here." /> : null}
        {items.map((a) => (
          <ApprovalCard key={a.id} approval={a} busy={decide.isPending} onDecide={(d, n) => onDecide(a.id, d, n)} />
        ))}
      </div>
    </>
  );
}
