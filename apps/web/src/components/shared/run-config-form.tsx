"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { LoaderCircle } from "@/components/animate-ui/icons/loader-circle";
import { Money } from "@/components/shared/live-number";
import { StatCard } from "@/components/shared/stat-card";
import { useToast } from "@/components/shared/use-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useSuiteList } from "@/lib/api/hooks/read";
import { useCreateRun, useRunEstimate } from "@/lib/api/hooks/write";
import { toApiError } from "@/lib/api/errors";
import { Skeleton } from "@/components/ui/skeleton";

import { budgetMicros, runStepSchema } from "./run-config";

/** Suite, repetitions and budget with a live dry-run estimate. Shared by the wizard and the start-run dialog. */
export function RunConfigForm({
  agentVersionId,
  initialSuiteId,
  onBack,
  submitLabel = "Start run",
}: {
  agentVersionId: string;
  initialSuiteId?: string;
  onBack?: () => void;
  submitLabel?: string;
}) {
  const router = useRouter();
  const toast = useToast();
  const suites = useSuiteList();
  const estimate = useRunEstimate();
  const create = useCreateRun();
  const [suiteId, setSuiteId] = useState(initialSuiteId ?? "");
  const [reps, setReps] = useState("1");
  const [budget, setBudget] = useState("2.00");

  const items = suites.data?.items;
  useEffect(() => {
    if (!suiteId && items?.length) setSuiteId(initialSuiteId && items.some((s) => s.id === initialSuiteId) ? initialSuiteId : items[0].id);
  }, [items, suiteId, initialSuiteId]);

  const parsed = useMemo(
    () => runStepSchema.safeParse({ suite_id: suiteId, repetitions: Number(reps), budget_dollars: Number(budget) }),
    [suiteId, reps, budget],
  );
  const body = useMemo(
    () =>
      parsed.success
        ? {
            suite_id: parsed.data.suite_id,
            agent_version_id: agentVersionId,
            repetitions: parsed.data.repetitions,
            budget_usd_micros: budgetMicros(parsed.data.budget_dollars),
            include_drafts: false,
          }
        : null,
    [parsed, agentVersionId],
  );
  const bodyKey = body ? JSON.stringify(body) : "";

  const { mutate: runEstimate, reset: resetEstimate } = estimate;
  useEffect(() => {
    if (!body) {
      resetEstimate();
      return;
    }
    const t = setTimeout(() => runEstimate(body), 500);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bodyKey]);

  const est = estimate.data;
  const overBudget = Boolean(est && body && est.estimate_usd_micros.expected > body.budget_usd_micros);
  const errors = !parsed.success ? Object.fromEntries(parsed.error.issues.map((i) => [String(i.path[0]), i.message])) : {};

  async function start() {
    if (!body) return;
    try {
      const run = await create.mutateAsync(body);
      router.push(`/runs/${run.id}`);
    } catch (e) {
      toast.error(e, "Could not start the run");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="suite">Suite</Label>
          {suites.isLoading ? (
            <Skeleton className="h-8 w-full" />
          ) : (
            <Select items={(items ?? []).map((s) => ({ value: s.id, label: s.name }))} value={suiteId} onValueChange={(v) => v && setSuiteId(v)}>
              <SelectTrigger id="suite" aria-label="Suite" className="w-full"><SelectValue placeholder="Choose a suite" /></SelectTrigger>
              <SelectContent>
                {(items ?? []).map((s) => (
                  <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          {errors.suite_id ? <p role="alert" className="text-destructive text-xs">{errors.suite_id}</p> : null}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="reps">Repetitions</Label>
          <Input id="reps" inputMode="numeric" value={reps} onChange={(e) => setReps(e.target.value)} aria-invalid={Boolean(errors.repetitions)} />
          {errors.repetitions ? <p role="alert" className="text-destructive text-xs">{errors.repetitions}</p> : null}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="budget">Budget (USD)</Label>
          <Input id="budget" inputMode="decimal" value={budget} onChange={(e) => setBudget(e.target.value)} aria-invalid={Boolean(errors.budget_dollars)} />
          {errors.budget_dollars ? <p role="alert" className="text-destructive text-xs">{errors.budget_dollars}</p> : null}
        </div>
      </div>

      <div data-testid="run-estimate" aria-live="polite">
        {estimate.isPending ? (
          <Skeleton className="h-20 w-full" />
        ) : estimate.error ? (
          <p role="alert" className="text-destructive text-sm">{toApiError(estimate.error).message}</p>
        ) : est ? (
          <div className="grid grid-cols-2 gap-3">
            <StatCard
              name="estimate"
              label="Estimated cost"
              value={<Money usdMicros={est.estimate_usd_micros.expected} />}
              hint="Expected cost; the range comes from the dry run"
              interval={`low ${(est.estimate_usd_micros.low / 1_000_000).toFixed(4)}, high ${(est.estimate_usd_micros.high / 1_000_000).toFixed(4)}`}
            />
            <StatCard name="episodes" label="Episodes" value={est.episode_count} />
            {est.errors.length > 0 ? <p className="text-destructive col-span-2 text-xs">{est.errors.map((e) => JSON.stringify(e)).join("; ")}</p> : null}
          </div>
        ) : (
          <p className="text-muted-foreground text-sm">Fill in the fields to see an estimate.</p>
        )}
        {overBudget ? <p role="alert" className="text-warning mt-2 text-sm">The estimate is above your budget. Raise the budget to start.</p> : null}
      </div>

      <div className="flex justify-end gap-2">
        {onBack ? <Button variant="ghost" onClick={onBack}>Back</Button> : null}
        <Button onClick={start} disabled={!body || create.isPending || overBudget || Boolean(estimate.error) || estimate.isPending}>
          {create.isPending ? <LoaderCircle size={14} animate loop /> : null}
          {submitLabel}
        </Button>
      </div>
    </div>
  );
}
