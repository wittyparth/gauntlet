"use client";

import { use } from "react";

import { CalibrationCard } from "@/components/rubrics/calibration-card";
import { RubricDetail } from "@/components/rubrics/rubric-detail";
import { SeverityBadge } from "@/components/shared/badges";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingCard } from "@/components/shared/loading";
import { PageHeader } from "@/components/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { useCalibrations, useRubric } from "@/lib/api/hooks/rubrics";

export default function RubricPage({ params }: { params: Promise<{ rubricId: string }> }) {
  const { rubricId } = use(params);
  const rubric = useRubric(rubricId);
  const cals = useCalibrations(rubricId);
  const r = rubric.data;
  return (
    <>
      <PageHeader
        title={r?.title ?? rubricId}
        breadcrumbs={[{ label: "Rubrics", href: "/rubrics" }, { label: rubricId }]}
        meta={
          r ? (
            <div className="flex items-center gap-2 text-xs">
              <span className="font-mono">v{r.version}</span>
              <SeverityBadge severity={r.severity} />
              {r.hard_fail ? <Badge variant="outline">hard fail</Badge> : null}
            </div>
          ) : null
        }
      />
      <div className="flex flex-col gap-3 p-4">
        {rubric.isLoading ? <LoadingCard lines={4} /> : null}
        {rubric.error ? <ErrorState error={rubric.error} onRetry={() => rubric.refetch()} /> : null}
        {cals.error ? <ErrorState error={cals.error} onRetry={() => cals.refetch()} /> : <CalibrationCard items={cals.data?.items} loading={cals.isLoading} />}
        {r ? <RubricDetail rubric={r} /> : null}
      </div>
    </>
  );
}
