"use client";

import { use, useState } from "react";

import { ModeControl } from "@/components/gateway/mode-control";
import { PolicyTestResults } from "@/components/gateway/policy-test-results";
import { RuleForm } from "@/components/gateway/rule-form";
import { RuleList } from "@/components/gateway/rule-list";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { JsonBlock } from "@/components/shared/json-block";
import { LoadingCard } from "@/components/shared/loading";
import { PageHeader } from "@/components/shared/page-header";
import { useToast } from "@/components/shared/use-toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  reportOf,
  useEnforcePolicy,
  usePolicy,
  usePolicyTests,
  useProposals,
  usePublishPolicy,
  useRunPolicyTest,
  useSaveRule,
} from "@/lib/api/hooks/policies";
import { useAgentVersions } from "@/lib/api/hooks/read";

export default function PolicyEditorPage({ params }: { params: Promise<{ policyId: string }> }) {
  const { policyId } = use(params);
  const toast = useToast();
  const policy = usePolicy(policyId);
  const proposals = useProposals(policyId);
  const tests = usePolicyTests(policyId);
  const versions = useAgentVersions(policy.data?.agent_id ?? "");
  const save = useSaveRule(policyId);
  const publish = usePublishPolicy(policyId);
  const enforce = useEnforcePolicy(policyId);
  const runTest = useRunPolicyTest(policyId);
  const [selected, setSelected] = useState<string | null>(null);
  const [versionId, setVersionId] = useState<string | null>(null);

  const p = policy.data;
  const list = proposals.data?.proposals ?? [];
  const current = list.find((x) => x.clause_id === (selected ?? list.find((y) => y.rule)?.clause_id));
  const latestTest = tests.data?.[0];
  const doneTest = tests.data?.find((t) => t.status === "done" && t.policy_version === p?.version);
  const report = reportOf(doneTest);
  const versionOptions = versions.data?.items ?? [];
  const testVersion = versionId ?? versionOptions[0]?.id ?? "";

  if (policy.error) {
    return <div className="p-4"><ErrorState error={policy.error} onRetry={() => policy.refetch()} /></div>;
  }
  return (
    <>
      <PageHeader
        title={p?.name ?? policyId}
        breadcrumbs={[{ label: "Gateway", href: "/gateway" }, { label: "Policies", href: "/gateway/policies" }, { label: p?.name ?? policyId }]}
        meta={
          p ? (
            <div className="flex flex-wrap items-center gap-3 text-xs">
              <span className="font-mono" data-testid="policy-version">v{p.version}</span>
              <Badge variant={p.status === "draft" ? "outline" : "secondary"}>{p.status}</Badge>
              {p.status === "published" ? (
                <ModeControl
                  current={{ mode: p.policy.mode, fail: p.policy.fail }}
                  report={report}
                  disabled={publish.isPending || enforce.isPending}
                  onApply={(next, override) => {
                    const op = next.mode === "enforce" && p.policy.mode === "shadow" ? enforce.mutateAsync(override) : publish.mutateAsync(next);
                    void toast.promise(op, { loading: "Saving the new version", success: "Saved as a new version", error: "Could not change the mode" }).catch(() => undefined);
                  }}
                />
              ) : (
                <Button size="sm" disabled={publish.isPending} onClick={() => void toast.promise(publish.mutateAsync({ mode: "shadow", fail: "open" }), { loading: "Publishing", success: "Published in shadow mode", error: "Could not publish" }).catch(() => undefined)}>
                  Publish
                </Button>
              )}
            </div>
          ) : null
        }
      />
      <div className="p-4">
        {policy.isLoading || proposals.isLoading ? (
          <LoadingCard lines={6} />
        ) : (
          <Tabs defaultValue="rules">
            <TabsList>
              <TabsTrigger value="rules">Rules {p ? <Badge variant="secondary" className="ml-1">{p.policy.rules.length}</Badge> : null}</TabsTrigger>
              <TabsTrigger value="tests">Test results</TabsTrigger>
              <TabsTrigger value="json">JSON</TabsTrigger>
            </TabsList>
            <TabsContent value="rules">
              {list.length === 0 ? (
                <EmptyState title="No clauses" body="This policy has no proposals to edit." />
              ) : (
                <div className="grid gap-4 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
                  <RuleList
                    proposals={list}
                    selected={current?.clause_id ?? null}
                    onSelect={setSelected}
                    onStatus={(clauseId, status) => void toast.promise(save.mutateAsync({ clauseId, status }), { loading: "Saving", success: `Rule ${status}`, error: "Could not change the rule" }).catch(() => undefined)}
                  />
                  {current?.rule ? (
                    <RuleForm
                      key={`${current.clause_id}:${JSON.stringify(current.rule)}`}
                      rule={current.rule}
                      saving={save.isPending}
                      onSave={(rule) => save.mutateAsync({ clauseId: current.clause_id, status: "edited", rule })}
                    />
                  ) : (
                    <EmptyState title="Select a rule" body="Pick a rule to edit its check, action and message." />
                  )}
                </div>
              )}
            </TabsContent>
            <TabsContent value="tests">
              <div className="flex flex-col gap-4 pt-2">
                <div className="flex flex-wrap items-center gap-2">
                  {versionOptions.length > 0 ? (
                    <Select items={versionOptions.map((v) => ({ value: v.id, label: v.label }))} value={testVersion} onValueChange={(v) => v && setVersionId(v)}>
                      <SelectTrigger size="sm" aria-label="Agent version to test" className="w-40"><SelectValue placeholder="Agent version" /></SelectTrigger>
                      <SelectContent>{versionOptions.map((v) => <SelectItem key={v.id} value={v.id}>{v.label}</SelectItem>)}</SelectContent>
                    </Select>
                  ) : null}
                  <Button size="sm" disabled={!testVersion || runTest.isPending} onClick={() => void toast.promise(runTest.mutateAsync(testVersion), { loading: "Starting the test", success: "Test started", error: "Could not start the test" }).catch(() => undefined)}>
                    Run test
                  </Button>
                  <span className="text-muted-foreground text-xs">Replays stored trajectories. No model calls.</span>
                </div>
                <PolicyTestResults test={latestTest} running={runTest.isPending} />
              </div>
            </TabsContent>
            <TabsContent value="json">{p ? <JsonBlock value={p.policy} label="policy" defaultOpen maxHeight={480} /> : null}</TabsContent>
          </Tabs>
        )}
      </div>
    </>
  );
}
