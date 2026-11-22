"use client";

import { ChevronRight } from "@/components/animate-ui/icons/chevron-right";
import { AddToPolicyDialog } from "@/components/findings/add-to-policy-dialog";
import { CheckTree } from "@/components/scenarios/check-tree";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { FindingDetail } from "@/lib/api/hooks/findings";

/** Shown only when the API suggests a rule; "Add to policy" puts it on a policy draft. */
export function SuggestedRuleCard({ rule }: { rule: NonNullable<FindingDetail["suggested_policy"]> }) {
  return (
    <Card size="sm" data-testid="suggested-rule-card">
      <Collapsible>
        <CardHeader>
          <CollapsibleTrigger className="group flex w-full items-center gap-2 text-left">
            <ChevronRight size={12} className="transition-transform group-data-open:rotate-90" />
            <CardTitle>
              <h2 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">Suggested policy rule</h2>
            </CardTitle>
            <Badge variant="secondary" className="ml-auto font-mono">
              {String(rule.action)}
            </Badge>
          </CollapsibleTrigger>
        </CardHeader>
        <CollapsibleContent>
          <CardContent className="flex flex-col gap-2">
            <p className="text-sm">{rule.description}</p>
            <CheckTree check={rule.when} />
            <div><AddToPolicyDialog rule={rule} /></div>
          </CardContent>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}
