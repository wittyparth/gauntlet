"use client";

import { usePathname, useRouter } from "next/navigation";

import { Radio } from "@/components/animate-ui/icons/radio";
import { BaselinePicker } from "@/components/compare/baseline-picker";
import { RunStatusBadge } from "@/components/shared/badges";
import { PageHeader } from "@/components/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { shortModel } from "@/components/models/draft";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useAgent } from "@/lib/api/hooks/read";
import type { Run } from "@/lib/api/models";

import { RunControls } from "./run-controls";
import { useRunLive } from "./run-live-context";

export function RunHeader({ run }: { run: Run }) {
  const router = useRouter();
  const pathname = usePathname();
  const live = useRunLive();
  const av = run.manifest?.agent_version;
  const agent = useAgent(av?.agent_id ?? "");
  const view = pathname.endsWith("/report") ? "report" : "console";
  const title = `${run.suite_id} on ${agent.data?.name ?? "agent"}${av ? ` ${av.label}` : ""}`;
  return (
    <>
      <PageHeader
        title={title}
        breadcrumbs={[{ label: "Runs", href: "/runs" }, { label: run.id }]}
        meta={
          <div className="flex items-center gap-2">
            <RunStatusBadge status={run.status} />
            {live.live ? (
              live.status === "open" ? (
                <Badge variant="outline" className="border-success/40 text-success"><Radio size={12} animate loop /> Live</Badge>
              ) : live.status === "closed" ? (
                <Badge variant="outline" className="border-warning/40 text-warning">Live updates paused</Badge>
              ) : (
                <Badge variant="outline">Connecting</Badge>
              )
            ) : null}
          </div>
        }
        actions={
          <>
            {run.status === "done" ? <BaselinePicker runId={run.id} suiteId={run.suite_id} /> : null}
            <RunControls runId={run.id} status={run.status} />
          </>
        }
      />
      {run.manifest?.model_roles ? (
        <p className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 px-4 pt-2 text-xs" data-testid="run-models">
          <span>Models</span>
          {Object.entries(run.manifest.model_roles)
            .filter(([role]) => role !== "embedder")
            .map(([role, model]) => (
              <span key={role}>
                {role.replace("_", " ")} <span className="text-foreground font-mono">{shortModel(model)}</span>
              </span>
            ))}
        </p>
      ) : null}
      <div className="px-4 pt-3">
        <ToggleGroup
          value={[view]}
          onValueChange={(v) => {
            const next = v[0];
            if (next && next !== view) router.push(next === "report" ? `/runs/${run.id}/report` : `/runs/${run.id}`);
          }}
          variant="outline"
          size="sm"
          aria-label="Run view"
        >
          <ToggleGroupItem value="console">Console</ToggleGroupItem>
          <ToggleGroupItem value="report">Report</ToggleGroupItem>
        </ToggleGroup>
      </div>
    </>
  );
}
