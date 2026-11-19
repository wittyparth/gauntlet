"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, use } from "react";

import { ScenarioJson } from "@/components/scenarios/scenario-json";
import { ScenarioSummary } from "@/components/scenarios/scenario-summary";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState, isNotFound } from "@/components/shared/error-state";
import { LoadingCard } from "@/components/shared/loading";
import { PageHeader } from "@/components/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useScenario } from "@/lib/api/hooks/read";

function Viewer({ scenarioId }: { scenarioId: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const view = params.get("view") === "json" ? "json" : "summary";
  const q = useScenario(scenarioId);

  if (q.isLoading) {
    return (
      <>
        <PageHeader title="Scenario" breadcrumbs={[{ label: "Scenarios", href: "/scenarios" }]} />
        <div className="grid gap-3 p-4 lg:grid-cols-2"><LoadingCard /><LoadingCard /></div>
      </>
    );
  }
  if (q.error) {
    return (
      <>
        <PageHeader title="Scenario" breadcrumbs={[{ label: "Scenarios", href: "/scenarios" }]} />
        <div className="p-4">
          {isNotFound(q.error) ? (
            <EmptyState title="Scenario not found" body="It may have been removed, or the link is wrong." action={<Button render={<Link href="/scenarios" />}>Go to scenarios</Button>} />
          ) : (
            <ErrorState error={q.error} onRetry={() => q.refetch()} />
          )}
        </div>
      </>
    );
  }
  const r = q.data;
  if (!r) return null;
  return (
    <>
      <PageHeader
        title={r.scenario.title}
        breadcrumbs={[{ label: "Scenarios", href: "/scenarios" }, { label: r.scenario.title }]}
        meta={
          <div className="flex items-center gap-2 text-xs">
            <span className="font-mono">v{r.version}</span>
            <Badge variant={r.status === "approved" ? "secondary" : "outline"}>{r.status}</Badge>
            <Badge variant="outline">{r.source}</Badge>
            <span className="text-muted-foreground font-mono">{r.id}</span>
          </div>
        }
      />
      <div className="p-4">
        <Tabs
          value={view}
          onValueChange={(v) => router.replace(v === "json" ? `/scenarios/${scenarioId}?view=json` : `/scenarios/${scenarioId}`, { scroll: false })}
        >
          <TabsList aria-label="Scenario view">
            <TabsTrigger value="summary">Summary</TabsTrigger>
            <TabsTrigger value="json">JSON</TabsTrigger>
          </TabsList>
          <TabsContent value="summary"><ScenarioSummary s={r.scenario} /></TabsContent>
          <TabsContent value="json"><ScenarioJson record={r} /></TabsContent>
        </Tabs>
      </div>
    </>
  );
}

export default function ScenarioPage({ params }: { params: Promise<{ scenarioId: string }> }) {
  const { scenarioId } = use(params);
  return (
    <Suspense>
      <Viewer scenarioId={scenarioId} />
    </Suspense>
  );
}
