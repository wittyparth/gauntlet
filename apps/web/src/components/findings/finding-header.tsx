import { CopyId } from "@/components/shared/copy-id";
import { SeverityBadge } from "@/components/shared/badges";
import { PageHeader } from "@/components/shared/page-header";
import type { FindingDetail } from "@/lib/api/hooks/findings";

import { FindingActions } from "./finding-actions";
import { reproSentence } from "./finding-utils";
import { StatusMenu } from "./status-menu";

export function FindingHeader({ finding }: { finding: FindingDetail }) {
  return (
    <PageHeader
      title={finding.title}
      breadcrumbs={[{ label: "Findings", href: "/findings" }, { label: finding.id }]}
      meta={<SeverityBadge severity={finding.severity} />}
      actions={
        <>
          <StatusMenu findingId={finding.id} status={finding.status} />
          <FindingActions findingId={finding.id} />
        </>
      }
    />
  );
}

/** The one-line facts under the header: what, how reliably, against which version. */
export function FindingFacts({ finding, versionLabel }: { finding: FindingDetail; versionLabel: string }) {
  return (
    <dl className="text-muted-foreground flex flex-wrap items-center gap-x-5 gap-y-1 text-xs">
      <div className="flex gap-1.5">
        <dt>Category</dt>
        <dd className="text-foreground font-mono">{finding.category}</dd>
      </div>
      <div className="flex gap-1.5">
        <dt>Reproducibility</dt>
        <dd className="text-foreground font-mono tabular-nums" data-testid="repro">
          {reproSentence(finding.reproducibility)}
        </dd>
      </div>
      <div className="flex gap-1.5">
        <dt>Agent</dt>
        <dd className="text-foreground">{versionLabel}</dd>
      </div>
      {finding.attack_id ? (
        <div className="flex gap-1.5">
          <dt>Attack</dt>
          <dd className="text-foreground font-mono">{finding.attack_id}</dd>
        </div>
      ) : null}
      <div className="flex items-center gap-1.5">
        <dt>Finding</dt>
        <dd className="text-foreground">
          <CopyId id={finding.id} />
        </dd>
      </div>
    </dl>
  );
}
