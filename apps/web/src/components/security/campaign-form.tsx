"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { hostCovered, isLoopback, targetHost } from "@/components/findings/finding-utils";
import { LoaderCircle } from "@/components/animate-ui/icons/loader-circle";
import { ChevronDown } from "@/components/animate-ui/icons/chevron-down";
import { Rocket } from "@/components/animate-ui/icons/rocket";
import { LiveNumber } from "@/components/shared/live-number";
import { StatCard } from "@/components/shared/stat-card";
import { useToast } from "@/components/shared/use-toast";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useAttackList, useTaxonomy } from "@/lib/api/hooks/attacks";
import { useScenarioList, useSuiteList } from "@/lib/api/hooks/read";
import {
  useAllVersions,
  useAttackScope,
  useCreateCampaign,
  useKillSwitch,
  useVerifications,
} from "@/lib/api/hooks/security";
import { toApiError } from "@/lib/api/errors";
import { formatUsd } from "@/lib/format";

import { CampaignAttackFields } from "./campaign-attack-fields";
import { CampaignTargetFields, type VersionState } from "./campaign-target-fields";
import {
  benignSuites,
  budgetMicros,
  campaignSchema,
  confirmationMatches,
  filterAttacks,
  isNarrowed,
  parseAttackIds,
  unknownAttackIds,
  type LibraryFilters,
} from "./campaign-schema";
import { versionLabel } from "./version-picker";

/** Launch an attack campaign: version, benign suite, attack selection, limits, typed confirmation. */
export function CampaignForm() {
  const router = useRouter();
  const toast = useToast();
  const versions = useAllVersions();
  const verifications = useVerifications();
  const suites = useSuiteList();
  const scenarios = useScenarioList();
  const taxonomy = useTaxonomy();
  const library = useAttackList({});
  const scope = useAttackScope();
  const kill = useKillSwitch();
  const create = useCreateCampaign();

  // Read from the URL after mount: `useSearchParams` would need a Suspense boundary, which hydrates
  // late and can see query data the server HTML did not have.
  const [versionId, setVersionId] = useState("");
  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get("version");
    if (wanted) setVersionId(wanted);
  }, []);
  const [suiteId, setSuiteId] = useState("");
  const [filters, setFilters] = useState<LibraryFilters>({ categories: [], vector: "all", source: "all", q: "" });
  const [categoriesTouched, setCategoriesTouched] = useState(false);
  const [adaptive, setAdaptive] = useState(false);
  const [reps, setReps] = useState("1");
  const [maxAttacks, setMaxAttacks] = useState("50");
  const [budget, setBudget] = useState("2.00");
  const [attackIdsRaw, setAttackIdsRaw] = useState("");
  const [injectTarget, setInjectTarget] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const verifiedHosts = useMemo(
    () => (verifications.data?.items ?? []).filter((v) => v.status === "verified").map((v) => v.host.toLowerCase()),
    [verifications.data],
  );
  const states = useMemo<VersionState[]>(
    () =>
      versions.items.map((item) => {
        const host = targetHost(item.version.target);
        const blocked = host !== null && !isLoopback(host) && !hostCovered(host, verifiedHosts) && !isHostLocalGuess(host);
        return { item, blocked, host };
      }),
    [versions.items, verifiedHosts],
  );
  const selected = states.find((s) => s.item.version.id === versionId && !s.blocked);

  // Defaults once data is there: first launchable version, first suite, every offered category.
  const versionsReady = !versions.isLoading && !verifications.isLoading;
  useEffect(() => {
    // Versions arrive agent by agent: wait for all of them, or a requested version would be replaced.
    if (!versionsReady) return;
    if (!versionId || !states.some((s) => s.item.version.id === versionId && !s.blocked)) {
      const first = states.find((s) => !s.blocked);
      if (first) setVersionId(first.item.version.id);
    }
  }, [states, versionId, versionsReady]);
  const suiteItems = useMemo(
    () => benignSuites(suites.data?.items ?? [], scenarios.data?.items ?? [], selected?.item.version.world_id ?? null),
    [suites.data, scenarios.data, selected],
  );
  useEffect(() => {
    if (!suiteItems.some((s) => s.id === suiteId)) setSuiteId(suiteItems[0]?.id ?? "");
  }, [suiteItems, suiteId]);
  const offered = useMemo(() => {
    const present = new Set((library.data ?? []).map((a) => a.category));
    return (taxonomy.data?.categories ?? []).filter((c) => !c.dangerous && present.has(c.id)).map((c) => c.id);
  }, [taxonomy.data, library.data]);
  useEffect(() => {
    if (!categoriesTouched && offered.length > 0) setFilters((f) => ({ ...f, categories: offered }));
  }, [offered, categoriesTouched]);

  const suite = suiteItems.find((s) => s.id === suiteId);
  const matched = useMemo(() => filterAttacks(library.data ?? [], filters), [library.data, filters]);
  const parsed = campaignSchema.safeParse({
    version_id: selected?.item.version.id ?? "",
    suite_id: suiteId,
    categories: filters.categories,
    repetitions: Number(reps),
    max_attacks: Number(maxAttacks),
    budget_dollars: Number(budget),
  });
  const errors = !parsed.success
    ? Object.fromEntries(parsed.error.issues.map((i) => [String(i.path[0]), i.message]))
    : {};
  const maxBudget = scope.data?.max_run_budget_usd_micros;
  const overScope = parsed.success && maxBudget !== undefined && budgetMicros(parsed.data.budget_dollars) > maxBudget;
  const engaged = kill.data?.engaged === true;
  const explicitIds = useMemo(() => parseAttackIds(attackIdsRaw), [attackIdsRaw]);
  const unknownIds = useMemo(() => unknownAttackIds(explicitIds, library.data ?? []), [explicitIds, library.data]);
  const explicit = explicitIds.length > 0;
  const available = explicit ? explicitIds.length - unknownIds.length : matched.length;
  const attackCount = Math.min(available, Number(maxAttacks) > 0 ? Number(maxAttacks) : available);
  const noMatches = parsed.success && available === 0;
  const canReview = parsed.success && unknownIds.length === 0 && !overScope && !engaged && !noMatches && !!suite && suite.scenarios.length > 0;
  const agentName = selected?.item.agentName ?? "";

  async function launch() {
    if (!parsed.success || !suite || !selected) return;
    try {
      const out = await create.mutateAsync({
        agent_version_id: selected.item.version.id,
        world_id: selected.item.version.world_id ?? "",
        benign_scenario_ids: suite.scenarios,
        ...(explicit
          ? { attack_ids: explicitIds, categories: null }
          : isNarrowed(filters)
            ? { attack_ids: matched.map((a) => a.id), categories: null }
            : { categories: filters.categories, attack_ids: null }),
        ...(injectTarget.trim() ? { inject_target: injectTarget.trim() } : {}),
        mode: adaptive ? "adaptive" : "static",
        mutations: [],
        seed: 0,
        repetitions: parsed.data.repetitions,
        max_attacks: parsed.data.max_attacks,
        budget_usd_micros: budgetMicros(parsed.data.budget_dollars),
      });
      toast.success(
        "Campaign started",
        `${out.attack_count} attacks queued${out.skipped.length > 0 ? `, ${out.skipped.length} skipped` : ""}`,
      );
      router.push(`/runs/${out.run.id}`);
    } catch (e) {
      setConfirming(false);
      toast.error(e, "Could not start the campaign");
    }
  }

  const loading = versions.isLoading || suites.isLoading || scenarios.isLoading || verifications.isLoading;
  const worldMissing = selected && !selected.item.version.world_id;

  return (
    <form
      className="flex max-w-3xl flex-col gap-6"
      onSubmit={(e) => {
        e.preventDefault();
        setSubmitted(true);
        if (canReview) {
          setTyped("");
          setConfirming(true);
        }
      }}
    >
      <CampaignTargetFields
        versions={states}
        versionId={versionId}
        onVersion={setVersionId}
        suites={suiteItems}
        suiteId={suiteId}
        onSuite={setSuiteId}
        loading={loading}
        errors={{ version: submitted ? errors.version_id : undefined, suite: submitted ? errors.suite_id : undefined }}
      />
      <CampaignAttackFields
        categories={taxonomy.data?.categories ?? []}
        library={library.data ?? []}
        filters={filters}
        onChange={(next) => {
          setCategoriesTouched(true);
          setFilters(next);
        }}
        loading={library.isLoading || taxonomy.isLoading}
        error={submitted ? errors.categories : undefined}
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="camp-max">Max attacks</Label>
          <Input id="camp-max" inputMode="numeric" value={maxAttacks} onChange={(e) => setMaxAttacks(e.target.value)} aria-invalid={Boolean(errors.max_attacks)} />
          {errors.max_attacks ? <p role="alert" className="text-destructive text-xs">{errors.max_attacks}</p> : null}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="camp-reps">Repetitions</Label>
          <Input id="camp-reps" inputMode="numeric" value={reps} onChange={(e) => setReps(e.target.value)} aria-invalid={Boolean(errors.repetitions)} />
          {errors.repetitions ? <p role="alert" className="text-destructive text-xs">{errors.repetitions}</p> : null}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="camp-budget">Budget (USD)</Label>
          <Input id="camp-budget" inputMode="decimal" value={budget} onChange={(e) => setBudget(e.target.value)} aria-invalid={Boolean(errors.budget_dollars) || overScope} />
          {errors.budget_dollars ? <p role="alert" className="text-destructive text-xs">{errors.budget_dollars}</p> : null}
          {overScope && maxBudget !== undefined ? (
            <p role="alert" className="text-destructive text-xs">Above the workspace limit of {formatUsd(maxBudget)} per run.</p>
          ) : null}
        </div>
      </div>

      {scope.data?.adaptive_enabled ? (
        <div className="flex items-center gap-3">
          <Switch id="camp-adaptive" checked={adaptive} onCheckedChange={setAdaptive} />
          <Label htmlFor="camp-adaptive" className="flex flex-col items-start gap-0.5 font-normal">
            Adaptive attacker
            <span className="text-muted-foreground text-xs">An attacker model refines failed attacks. Costs more; static runs replay the library as is.</span>
          </Label>
        </div>
      ) : null}

      <Collapsible className="flex flex-col gap-3" data-testid="advanced">
        <CollapsibleTrigger className="text-muted-foreground hover:text-foreground flex w-fit items-center gap-1.5 text-sm font-medium">
          <ChevronDown size={14} animateOnHover />
          Advanced
        </CollapsibleTrigger>
        <CollapsibleContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="camp-attack-ids">Attack ids</Label>
            <Textarea
              id="camp-attack-ids"
              className="font-mono text-xs"
              rows={2}
              placeholder="atk_001, atk_002"
              value={attackIdsRaw}
              onChange={(e) => setAttackIdsRaw(e.target.value)}
              aria-invalid={unknownIds.length > 0}
            />
            <p className="text-muted-foreground text-xs">
              Comma separated ids from the attack library ({library.data?.length ?? 0} available). When set, these replace the category and filter selection.
            </p>
            {unknownIds.length > 0 ? (
              <p role="alert" className="text-destructive text-xs">Not in the library: {unknownIds.slice(0, 5).join(", ")}{unknownIds.length > 5 ? ", ..." : ""}</p>
            ) : null}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="camp-inject">Injection target</Label>
            <Input id="camp-inject" className="font-mono text-xs" placeholder="orders/ord_1001/notes" value={injectTarget} onChange={(e) => setInjectTarget(e.target.value)} autoComplete="off" />
            <p className="text-muted-foreground text-xs">A tool name or state path where tool-result attacks inject. Default: the first untrusted tool of the world.</p>
          </div>
        </CollapsibleContent>
      </Collapsible>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3" aria-live="polite">
        <StatCard name="attacks" label="Attacks selected" value={<LiveNumber value={attackCount} />} hint="Library attacks matching your filters, capped by Max attacks" />
        <StatCard name="episodes" label="Benign tasks" value={<LiveNumber value={suite?.scenarios.length ?? 0} />} />
        <StatCard
          name="budget-cap"
          label="Budget cap"
          value={Number.isFinite(Number(budget)) ? formatUsd(budgetMicros(Number(budget))) : "n/a"}
          hint="The run stops when this is spent"
        />
      </div>

      {noMatches ? (
        <Alert>
          <AlertTitle>No attacks match</AlertTitle>
          <AlertDescription>Loosen the filters or pick more categories.</AlertDescription>
        </Alert>
      ) : null}
      {worldMissing ? (
        <Alert variant="destructive">
          <AlertTitle>This version has no world</AlertTitle>
          <AlertDescription>Campaigns place attacks into a world. Add one to the agent version first.</AlertDescription>
        </Alert>
      ) : null}
      {engaged ? (
        <Alert variant="destructive" role="alert" data-testid="killswitch-block">
          <AlertTitle>The kill switch is engaged</AlertTitle>
          <AlertDescription>New campaigns are refused until it is released.</AlertDescription>
        </Alert>
      ) : null}

      <div className="flex justify-end">
        <Button type="submit" disabled={create.isPending || engaged || !!worldMissing || (submitted && !canReview)}>
          {create.isPending ? <LoaderCircle size={14} animate loop /> : <Rocket size={14} animateOnHover />}
          Review and launch
        </Button>
      </div>

      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Attack {agentName}?</AlertDialogTitle>
            <AlertDialogDescription>
              This sends {attackCount} real attack payloads to {selected ? versionLabel(selected.item) : "the agent"}, up to {formatUsd(budgetMicros(Number(budget) || 0))}. Only attack agents you own. Type the agent name to confirm.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="camp-confirm">
              Type <span className="font-mono">{agentName}</span>
            </Label>
            <Input id="camp-confirm" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
          </div>
          {create.error ? <p role="alert" className="text-destructive text-sm">{toApiError(create.error).message}</p> : null}
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={!confirmationMatches(typed, agentName) || create.isPending}
              onClick={() => void launch()}
            >
              {create.isPending ? <LoaderCircle size={14} animate loop /> : null}
              Launch campaign
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </form>
  );
}

/**
 * The API decides which hosts are local (`GAUNTLET_LOCAL_TARGET_HOSTS`) and does not publish the
 * list. Compose service names without a dot are the only hosts the UI treats as local; the server
 * is still the authority and its refusal is shown in the dialog.
 */
function isHostLocalGuess(host: string): boolean {
  return !host.includes(".");
}
