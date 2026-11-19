"use client";

import { RunConfigForm } from "@/components/shared/run-config-form";

export function StepRun({ versionId, suiteId, onBack }: { versionId: string; suiteId: string; onBack: () => void }) {
  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <h2 className="text-base font-medium">Ready to run</h2>
      <RunConfigForm agentVersionId={versionId} initialSuiteId={suiteId} onBack={onBack} />
    </div>
  );
}
