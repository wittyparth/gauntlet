"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { useAllVersions } from "@/lib/api/hooks/security";
import type { components } from "@/lib/api/schema";

import { versionLabel } from "./version-picker";

type Item = ReturnType<typeof useAllVersions>["items"][number];
type Suite = components["schemas"]["SuiteOut"];

export type VersionState = { item: Item; blocked: boolean; host: string | null };

/** Agent version (remote targets without ownership verification are disabled) and the benign suite. */
export function CampaignTargetFields({
  versions,
  versionId,
  onVersion,
  suites,
  suiteId,
  onSuite,
  loading,
  errors,
}: {
  versions: VersionState[];
  versionId: string;
  onVersion: (id: string) => void;
  suites: Suite[];
  suiteId: string;
  onSuite: (id: string) => void;
  loading: boolean;
  errors: { version?: string; suite?: string };
}) {
  const blocked = versions.filter((v) => v.blocked);
  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="camp-version">Agent version</Label>
          {loading ? (
            <Skeleton className="h-8 w-full" />
          ) : (
            <Select
              items={versions.map((v) => ({ value: v.item.version.id, label: versionLabel(v.item) }))}
              value={versionId}
              onValueChange={(v) => v && onVersion(v)}
            >
              <SelectTrigger id="camp-version" aria-label="Agent version" className="w-full">
                <SelectValue placeholder="Choose a version" />
              </SelectTrigger>
              <SelectContent>
                {versions.map((v) => {
                  const row = (
                    <SelectItem key={v.item.version.id} value={v.item.version.id} disabled={v.blocked}>
                      {versionLabel(v.item)}
                      {v.blocked ? <span className="text-muted-foreground ml-1 text-xs">(not verified)</span> : null}
                    </SelectItem>
                  );
                  return v.blocked ? (
                    <Tooltip key={v.item.version.id}>
                      <TooltipTrigger render={<div />}>{row}</TooltipTrigger>
                      <TooltipContent>
                        {v.host} has not passed ownership verification. Verify it before attacking it.
                      </TooltipContent>
                    </Tooltip>
                  ) : (
                    row
                  );
                })}
              </SelectContent>
            </Select>
          )}
          {errors.version ? (
            <p role="alert" className="text-destructive text-xs">
              {errors.version}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="camp-suite">Benign suite</Label>
          {loading ? (
            <Skeleton className="h-8 w-full" />
          ) : (
            <Select
              items={suites.map((s) => ({ value: s.id, label: s.name }))}
              value={suiteId}
              onValueChange={(v) => v && onSuite(v)}
            >
              <SelectTrigger id="camp-suite" aria-label="Benign suite" className="w-full">
                <SelectValue placeholder="Choose a suite" />
              </SelectTrigger>
              <SelectContent>
                {suites.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <p className="text-muted-foreground text-xs">Attacks are placed into these everyday tasks, so each one also checks that normal work still succeeds.</p>
          {errors.suite ? (
            <p role="alert" className="text-destructive text-xs">
              {errors.suite}
            </p>
          ) : null}
        </div>
      </div>
      {blocked.length > 0 ? (
        <Alert data-testid="unverified-alert">
          <AlertTitle>{blocked.length === 1 ? "1 version is disabled" : `${blocked.length} versions are disabled`}</AlertTitle>
          <AlertDescription>
            Remote targets must prove ownership before they can be attacked:{" "}
            {blocked.map((b) => `${versionLabel(b.item)} (${b.host})`).join(", ")}.
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}
