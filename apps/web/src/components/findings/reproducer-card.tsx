"use client";

import { CopyButton, CopyButtonIcon } from "@animate-ui/react/primitives/buttons/copy";

import { CircleCheck } from "@/components/animate-ui/icons/circle-check";
import { Copy } from "@/components/animate-ui/icons/copy";
import { CheckTree } from "@/components/scenarios/check-tree";
import { JsonBlock } from "@/components/shared/json-block";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { FindingDetail } from "@/lib/api/hooks/findings";

import { attackPayload, objectiveCheck } from "./finding-utils";

/** The minimal scenario that reproduces the finding. Payload is shown as text, never rendered. */
export function ReproducerCard({ reproducer }: { reproducer: FindingDetail["reproducer"] }) {
  const payload = attackPayload(reproducer);
  const objective = objectiveCheck(reproducer);
  const json = JSON.stringify(reproducer, null, 2);
  return (
    <Card size="sm" data-testid="reproducer-card">
      <CardHeader>
        <CardTitle>
          <h2 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">Reproducer</h2>
        </CardTitle>
        <CardAction>
          <CopyButton asChild content={json} delay={1500}>
            <Button variant="ghost" size="xs" aria-label="Copy scenario JSON">
              <CopyButtonIcon icon={<Copy size={12} />} copiedIcon={<CircleCheck size={12} animate />} />
              Copy JSON
            </Button>
          </CopyButton>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <section className="flex flex-col gap-1">
          <h3 className="text-muted-foreground text-xs">Goal</h3>
          <p className="text-sm">{reproducer.goal}</p>
        </section>
        {payload ? (
          <section className="flex flex-col gap-1">
            <h3 className="text-muted-foreground text-xs">Attack payload</h3>
            <pre
              className="bg-muted/40 max-h-48 overflow-auto rounded-md border p-2 font-mono text-xs break-words whitespace-pre-wrap"
              data-testid="attack-payload"
            >
              {payload}
            </pre>
          </section>
        ) : null}
        {objective ? (
          <section className="flex flex-col gap-1">
            <h3 className="text-muted-foreground text-xs">Objective: the attack succeeds when</h3>
            <CheckTree check={objective} />
          </section>
        ) : null}
        <JsonBlock value={reproducer} label="full scenario" defaultOpen={false} />
      </CardContent>
    </Card>
  );
}
