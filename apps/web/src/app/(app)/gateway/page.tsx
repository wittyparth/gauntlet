"use client";

import { useState } from "react";

import { DecisionDetail } from "@/components/gateway/decision-detail";
import { DecisionTable } from "@/components/gateway/decision-table";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { FilterBar } from "@/components/shared/filter-bar";
import { PageHeader } from "@/components/shared/page-header";
import { StatCard } from "@/components/shared/stat-card";
import { Badge } from "@/components/ui/badge";
import { useApprovals } from "@/lib/api/hooks/approvals";
import { DECISION_POLL_MS, useGatewayDecisions, useGatewayStats, type Decision } from "@/lib/api/hooks/gateway";
import { usePolicyList } from "@/lib/api/hooks/policies";

const FACETS = [
  { value: "all", label: "All" },
  { value: "block", label: "Block" },
  { value: "require_approval", label: "Require approval" },
  { value: "redact", label: "Redact" },
  { value: "log", label: "Log" },
];

export default function GatewayConsolePage() {
  const [facet, setFacet] = useState("all");
  const [tool, setTool] = useState("");
  const [open, setOpen] = useState<Decision | null>(null);
  const decisions = useGatewayDecisions({ action: facet === "all" ? undefined : facet, tool: tool.trim() || undefined });
  const stats = useGatewayStats("1h");
  const pending = useApprovals("pending");
  const policies = usePolicyList();
  const active = policies.data?.find((p) => p.status === "published");
  const blocked = stats.data?.by_action.block ?? 0;
  const items = decisions.data?.items ?? [];
  return (
    <>
      <PageHeader
        title="Gateway"
        breadcrumbs={[{ label: "Gateway" }]}
        meta={
          <div className="flex items-center gap-2 text-xs">
            {active ? (
              <>
                <span>policy: {active.name} v{active.version}</span>
                <Badge variant="outline" className={active.policy.mode === "enforce" ? "border-destructive/40 text-destructive" : ""}>{active.policy.mode}</Badge>
              </>
            ) : null}
            <Badge variant="outline" className="border-success/40 text-success" title={`No decision stream: refreshed every ${DECISION_POLL_MS / 1000} s while this tab is visible`}>
              Live (polling)
            </Badge>
          </div>
        }
      />
      <div className="flex flex-col gap-4 p-4">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard name="decisions" label="Decisions, last hour" value={stats.data?.total ?? "n/a"} />
          <StatCard name="blocked" label="Blocked" value={blocked} />
          <StatCard name="pending" label="Approvals pending" value={pending.data?.length ?? "n/a"} />
          <StatCard name="p50" label="Gateway overhead p50" value={stats.data?.overhead_us.p50 != null ? `${Math.round(stats.data.overhead_us.p50)} µs` : "n/a"} interval={stats.data?.overhead_us.p95 != null ? `p95 ${Math.round(stats.data.overhead_us.p95)} µs` : undefined} />
        </div>
        <FilterBar facets={FACETS} facet={facet} onFacetChange={setFacet} search={tool} onSearchChange={setTool} searchLabel="Filter by tool" />
        {decisions.error ? (
          <ErrorState error={decisions.error} onRetry={() => decisions.refetch()} />
        ) : decisions.data && items.length === 0 ? (
          <EmptyState title="No traffic yet" body="Wrap your agent's tool calls with the Gauntlet gateway middleware and its decisions will appear here." />
        ) : (
          <DecisionTable decisions={items} isLoading={decisions.isLoading} onOpen={setOpen} />
        )}
      </div>
      <DecisionDetail decision={open} onClose={() => setOpen(null)} />
    </>
  );
}
