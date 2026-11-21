"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";

import { AuditTable } from "@/components/security/audit-table";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { PageHeader } from "@/components/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuditChain, useAuditLog } from "@/lib/api/hooks/security";

function ChainBadge() {
  const q = useAuditChain();
  if (!q.data) return null;
  return q.data.ok ? (
    <Badge variant="outline" className="border-success/40 text-success" data-testid="chain-ok">
      Chain intact ({q.data.checked} entries)
    </Badge>
  ) : (
    <Badge variant="outline" className="border-destructive/40 text-destructive" data-testid="chain-broken">
      Chain broken at {q.data.first_bad_id}
    </Badge>
  );
}

function FilterSelect({ label, value, values, onChange }: { label: string; value: string; values: string[]; onChange: (v: string) => void }) {
  const items = [{ value: "all", label }, ...values.map((v) => ({ value: v, label: v }))];
  return (
    <Select items={items} value={value} onValueChange={(v) => v && onChange(v)}>
      <SelectTrigger size="sm" aria-label={label} className="w-48">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {items.map((i) => (
          <SelectItem key={i.value} value={i.value}>
            {i.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function Audit() {
  const router = useRouter();
  const params = useSearchParams();
  const action = params.get("action") ?? "all";
  const subject = params.get("subject") ?? "all";
  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value === "all") next.delete(key);
    else next.set(key, value);
    router.replace(next.toString() ? `/security/audit?${next}` : "/security/audit", { scroll: false });
  };
  const q = useAuditLog({ action, subject_type: subject });
  // Filter options come from an unfiltered read so choosing one does not shrink the other list.
  const all = useAuditLog({});
  const actions = useMemo(() => [...new Set((all.data?.items ?? []).map((r) => r.action))].sort(), [all.data]);
  const subjects = useMemo(() => [...new Set((all.data?.items ?? []).map((r) => r.subject_type))].sort(), [all.data]);
  const rows = q.data?.items ?? [];
  const filtered = action !== "all" || subject !== "all";
  return (
    <>
      <PageHeader
        title="Audit log"
        breadcrumbs={[{ label: "Security", href: "/security" }, { label: "Audit log" }]}
        meta={<ChainBadge />}
      />
      <div className="flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <FilterSelect label="Any action" value={action} values={actions} onChange={(v) => setParam("action", v)} />
          <FilterSelect label="Any subject" value={subject} values={subjects} onChange={(v) => setParam("subject", v)} />
          <span className="text-muted-foreground text-xs">{rows.length} entries, newest first</span>
        </div>
        {q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : (
          <AuditTable
            rows={rows}
            isLoading={q.isLoading}
            emptyState={
              filtered ? (
                <EmptyState title="No entries match these filters" action={<Button variant="outline" onClick={() => router.replace("/security/audit")}>Clear filters</Button>} />
              ) : (
                <EmptyState title="Nothing recorded yet" body="Campaigns, status changes, kill switch use and target verification are written here." />
              )
            }
          />
        )}
      </div>
    </>
  );
}

export default function AuditPage() {
  return (
    <Suspense>
      <Audit />
    </Suspense>
  );
}
