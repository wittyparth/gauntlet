"use client";

import { useEffect, useState } from "react";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { useToast } from "@/components/shared/use-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useModelCatalog, useModelSettings } from "@/lib/api/hooks/read";
import { usePutModelSettings } from "@/lib/api/hooks/write";
import type { RoleChoice } from "@/lib/api/models";

import { ROLE_LABELS, ROLE_ORDER, rolesToSave } from "./draft";
import { ModelSelect } from "./model-select";

export function ModelsForm() {
  const catalog = useModelCatalog();
  const settings = useModelSettings();
  const put = usePutModelSettings();
  const toast = useToast();
  const [draft, setDraft] = useState<Record<string, RoleChoice> | null>(null);

  useEffect(() => {
    if (settings.data) setDraft(structuredClone(settings.data.roles) as Record<string, RoleChoice>);
  }, [settings.data]);

  const err = catalog.error ?? settings.error;
  if (err) return <ErrorState error={err} onRetry={() => { void catalog.refetch(); void settings.refetch(); }} />;
  if (!catalog.data || !settings.data || !draft) {
    return <Skeleton className="h-72 w-full max-w-3xl" data-testid="loading-rows" />;
  }
  if (catalog.data.models.length === 0) return <EmptyState title="No models available" />;

  const models = catalog.data.models;
  const dirty = ROLE_ORDER.some(
    (r) => draft[r]?.model !== settings.data.roles[r]?.model || draft[r]?.reasoning !== settings.data.roles[r]?.reasoning,
  );

  const save = () =>
    toast.promise(put.mutateAsync(rolesToSave(settings.data, draft)), {
      loading: "Saving models",
      success: "Models saved",
      error: "Could not save models",
    });
  const reset = () =>
    toast.promise(put.mutateAsync({}), {
      loading: "Resetting models",
      success: "Models reset to defaults",
      error: "Could not reset models",
    });

  return (
    <div className="flex max-w-3xl flex-col gap-3">
      <p className="text-muted-foreground text-sm">
        Choose the model each part of a run uses. A run keeps the models it started with, and the report shows them.
      </p>
      {ROLE_ORDER.map((role) => {
        const choice = draft[role];
        const meta = ROLE_LABELS[role];
        const model = models.find((m) => m.id === choice.model);
        const canTurnOff = model?.supports_reasoning_off ?? false;
        const reasoningOn = choice.reasoning !== "off";
        return (
          <Card key={role} data-testid={`role-${role}`}>
            <CardContent className="flex flex-wrap items-center justify-between gap-3 p-3">
              <div className="flex min-w-48 flex-col">
                <Label htmlFor={`model-${role}`} className="text-sm font-medium">{meta.label}</Label>
                <span className="text-muted-foreground text-xs">{meta.hint}</span>
                {settings.data.overridden.includes(role) ? (
                  <span className="text-muted-foreground text-xs">Set for this workspace</span>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-4">
                <ModelSelect
                  id={`model-${role}`}
                  catalog={models}
                  value={choice.model}
                  role={role}
                  label={`${meta.label} model`}
                  onChange={(id) => setDraft({ ...draft, [role]: { ...choice, model: id } })}
                />
                <div className="flex items-center gap-2">
                  <Switch
                    id={`reasoning-${role}`}
                    aria-label={`${meta.label} reasoning`}
                    checked={reasoningOn}
                    disabled={!canTurnOff}
                    onCheckedChange={(on) =>
                      setDraft({ ...draft, [role]: { ...choice, reasoning: on ? "default" : "off" } })
                    }
                  />
                  <Label htmlFor={`reasoning-${role}`} className="text-xs">Reasoning</Label>
                </div>
              </div>
            </CardContent>
          </Card>
        );
      })}
      <div className="flex items-center gap-2">
        <Button onClick={save} disabled={!dirty || put.isPending}>Save</Button>
        <Button variant="outline" onClick={reset} disabled={put.isPending}>Reset to defaults</Button>
      </div>
    </div>
  );
}
