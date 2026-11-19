"use client";

import { JsonBlock } from "@/components/shared/json-block";
import type { ScenarioRecord } from "@/lib/api/models";

/** The scenario document exactly as stored. */
export function ScenarioJson({ record }: { record: ScenarioRecord }) {
  return <JsonBlock value={record.scenario} label="scenario" defaultOpen maxHeight={640} />;
}
