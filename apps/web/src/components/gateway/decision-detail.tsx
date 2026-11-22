"use client";

import Link from "next/link";

import { CheckTree } from "@/components/scenarios/check-tree";
import { SeverityBadge } from "@/components/shared/badges";
import { JsonBlock } from "@/components/shared/json-block";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { Decision } from "@/lib/api/hooks/gateway";
import { usePolicy } from "@/lib/api/hooks/policies";

import { ActionBadge } from "./decision-table";

function Rule({ decision }: { decision: Decision }) {
  const policy = usePolicy(decision.policy_id);
  const rule = policy.data?.policy.rules.find((r) => r.id === decision.rule_id);
  if (!rule) return null;
  return (
    <section className="flex flex-col gap-1" aria-label="Rule">
      <h3 className="text-sm font-medium">Rule {rule.id}</h3>
      <p className="text-sm">{rule.description}</p>
      <CheckTree check={rule.when} />
    </section>
  );
}

export function DecisionDetail({ decision, onClose }: { decision: Decision | null; onClose: () => void }) {
  return (
    <Sheet open={decision != null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl" data-testid="decision-detail">
        {decision ? (
          <>
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">
                <ActionBadge action={decision.action} />
                <span className="font-mono text-sm" data-testid="detail-rule">{decision.rule_id ?? "no rule"}</span>
                {decision.severity ? <SeverityBadge severity={decision.severity} /> : null}
              </SheetTitle>
              <SheetDescription>
                {decision.kind === "tool_call" ? `Tool ${decision.tool ?? "?"}` : "Model output"}, {decision.mode} mode, policy {decision.policy_id} v{decision.policy_version}
                {!decision.enforced && decision.would_have ? `. Shadow: it would have ${decision.would_have.replace("_", " ")}.` : "."}
              </SheetDescription>
            </SheetHeader>
            <div className="flex flex-col gap-4 px-4 pb-4">
              {decision.message ? <p className="text-sm">{decision.message}</p> : null}
              {decision.guard_error ? <p className="text-destructive text-sm">Guard error: {decision.guard_error}</p> : null}
              {decision.rule_id ? <Rule decision={decision} /> : null}
              <JsonBlock value={decision.args ?? {}} label="proposed action" defaultOpen />
              {decision.evidence.length > 0 ? (
                <section aria-label="Evidence">
                  <h3 className="text-sm font-medium">Evidence</h3>
                  <ul className="flex flex-col gap-1 text-sm">
                    {decision.evidence.map((e, i) => (
                      <li key={i}>
                        {decision.episode_id ? (
                          <Link href={`/episodes/${decision.episode_id}#e-${e.seq}`} className="font-mono text-xs underline" data-testid="evidence-link">[{e.seq}]</Link>
                        ) : (
                          <span className="text-muted-foreground font-mono text-xs">[{e.seq}]</span>
                        )}{" "}
                        {e.quote ?? e.note ?? ""}
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
              {decision.episode_id ? (
                <Link href={`/episodes/${decision.episode_id}`} className="text-sm underline" data-testid="episode-link">Open the simulated episode</Link>
              ) : null}
              <p className="text-muted-foreground font-mono text-xs">session {decision.session_id}, overhead {decision.overhead_us} µs</p>
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
