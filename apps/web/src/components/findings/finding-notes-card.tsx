import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { FindingDetail } from "@/lib/api/hooks/findings";
import { timeAgo } from "@/lib/format";

import { statusLabel } from "./finding-utils";

/** Root cause hint and the status history, both straight from the finding. */
export function FindingNotesCard({ finding }: { finding: FindingDetail }) {
  if (!finding.root_cause_hint && finding.notes.length === 0) return null;
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>
          <h2 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">History</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {finding.root_cause_hint ? (
          <section>
            <h3 className="text-muted-foreground text-xs">Root cause hint</h3>
            <p className="text-sm">{finding.root_cause_hint}</p>
          </section>
        ) : null}
        {finding.notes.length > 0 ? (
          <ol className="flex flex-col gap-1.5" data-testid="finding-history">
            {finding.notes.map((n, i) => (
              <li key={`${n.ts}-${i}`} className="flex flex-wrap items-baseline gap-x-2 text-xs">
                <span className="text-muted-foreground w-16 shrink-0">{timeAgo(n.ts)}</span>
                {n.to_status ? (
                  <span className="font-medium">
                    {n.from_status ? `${statusLabel(n.from_status)} to ` : "Set to "}
                    {statusLabel(n.to_status)}
                  </span>
                ) : null}
                <span className="text-muted-foreground">{n.actor}</span>
                {n.note ? <span className="basis-full pl-[4.5rem]">{n.note}</span> : null}
              </li>
            ))}
          </ol>
        ) : null}
      </CardContent>
    </Card>
  );
}
