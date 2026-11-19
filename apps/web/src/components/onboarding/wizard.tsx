"use client";

import { useRouter, useSearchParams } from "next/navigation";

import { Stepper } from "@/components/shared/stepper";

import { StepAgent } from "./step-agent";
import { StepRun } from "./step-run";
import { StepScenarios } from "./step-scenarios";
import { StepTarget } from "./step-target";

export function Wizard() {
  const router = useRouter();
  const params = useSearchParams();
  const agent = params.get("agent");
  const version = params.get("version");
  const suite = params.get("suite");
  const requested = Math.min(4, Math.max(1, Number(params.get("step") ?? "1") || 1));
  const reached = suite && version && agent ? 3 : version && agent ? 2 : agent ? 1 : 0;
  const current = Math.min(requested - 1, reached);

  const go = (step: number, patch: Record<string, string | null> = {}) => {
    const next = new URLSearchParams(params.toString());
    next.set("step", String(step));
    for (const [k, v] of Object.entries(patch)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    router.replace(`/onboarding?${next.toString()}`, { scroll: false });
  };

  return (
    <Stepper
      current={current}
      reached={reached}
      onChange={(i) => go(i + 1)}
      steps={[
        { value: "agent", label: "Agent", content: <StepAgent onDone={(id) => go(2, { agent: id, version: null, suite: null })} /> },
        {
          value: "target",
          label: "Target",
          content: agent ? <StepTarget agentId={agent} onBack={() => go(1)} onDone={(v) => go(3, { version: v, suite: null })} /> : null,
        },
        {
          value: "scenarios",
          label: "Scenarios",
          content: agent && version ? <StepScenarios agentId={agent} suiteId={suite} onBack={() => go(2)} onDone={(s) => go(4, { suite: s })} /> : null,
        },
        {
          value: "run",
          label: "Run",
          content: version && suite ? <StepRun versionId={version} suiteId={suite} onBack={() => go(3)} /> : null,
        },
      ]}
    />
  );
}
