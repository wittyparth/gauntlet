"use client";

import { useState } from "react";

import { LoaderCircle } from "@/components/animate-ui/icons/loader-circle";
import { EmptyState } from "@/components/shared/empty-state";
import { LiveStatusText } from "@/components/shared/live-status-text";
import { LoadingRows } from "@/components/shared/loading";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { toApiError } from "@/lib/api/errors";
import { useSuiteList } from "@/lib/api/hooks/read";
import { useGenerateScenarios } from "@/lib/api/hooks/write";

export function StepScenarios({ agentId, suiteId, onBack, onDone }: { agentId: string; suiteId: string | null; onBack: () => void; onDone: (suiteId: string) => void }) {
  const [source, setSource] = useState<"pack" | "generate">("pack");
  const suites = useSuiteList();
  const generate = useGenerateScenarios(agentId);
  const [picked, setPicked] = useState(suiteId ?? "");
  const items = suites.data?.items ?? [];

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <h2 className="text-base font-medium">Which scenarios should it face?</h2>
      <ToggleGroup value={[source]} onValueChange={(v) => v[0] && setSource(v[0] as "pack" | "generate")} variant="outline" aria-label="Scenario source">
        <ToggleGroupItem value="pack">Use a pack suite</ToggleGroupItem>
        <ToggleGroupItem value="generate">Generate from profile</ToggleGroupItem>
      </ToggleGroup>

      {source === "pack" ? (
        suites.isLoading ? (
          <LoadingRows rows={3} />
        ) : items.length === 0 ? (
          <EmptyState title="No pack suites loaded" body="Load a scenario pack on the server, then come back." />
        ) : (
          <RadioGroup value={picked} onValueChange={(v) => setPicked(String(v))} aria-label="Suite" className="gap-2">
            {items.map((s) => (
              <label key={s.id} htmlFor={`suite-${s.id}`} className="hover:bg-muted/50 flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2">
                <RadioGroupItem id={`suite-${s.id}`} value={s.id} />
                <span className="flex-1">{s.name}</span>
                <span className="text-muted-foreground font-mono text-xs">{s.scenarios.length} scenarios</span>
              </label>
            ))}
          </RadioGroup>
        )
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-muted-foreground text-sm">Gauntlet drafts scenarios from the agent profile. You review them before anything runs.</p>
          <div>
            <Button onClick={() => generate.mutate()} disabled={generate.isPending}>
              {generate.isPending ? <LoaderCircle size={14} animate loop /> : null}
              Generate scenarios
            </Button>
          </div>
          {generate.isPending ? <LiveStatusText text="Generating scenarios" /> : null}
          {generate.error ? (
            <EmptyState title="Nothing generated" body={`${toApiError(generate.error).message} Use a pack suite instead, or add more detail to the profile.`} action={<Button variant="outline" onClick={onBack}>Back to step 2</Button>} />
          ) : null}
        </div>
      )}
      <div className="flex justify-between">
        <Button variant="ghost" onClick={onBack}>Back</Button>
        <Button disabled={source !== "pack" || !picked} onClick={() => onDone(picked)}>Continue</Button>
      </div>
    </div>
  );
}
