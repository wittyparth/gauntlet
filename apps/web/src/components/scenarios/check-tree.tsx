"use client";

import { ChevronRight } from "@/components/animate-ui/icons/chevron-right";
import { JsonBlock } from "@/components/shared/json-block";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

import { describeCheck } from "./describe-check";

function Node({ check, depth }: { check: unknown; depth: number }) {
  const d = describeCheck(check);
  if (!d.known) {
    return (
      <div className="py-1" data-testid="check-node" data-type="unknown">
        <JsonBlock value={check} label="check" defaultOpen />
      </div>
    );
  }
  if (d.children.length === 0) {
    return (
      <div className="flex items-start gap-2 py-1" data-testid="check-node" data-type={d.type}>
        <Badge variant="secondary" className="font-mono">{d.type}</Badge>
        <span className="min-w-0 font-mono text-xs break-words">{d.summary}</span>
      </div>
    );
  }
  return (
    <Collapsible defaultOpen={depth < 3} data-testid="check-node" data-type={d.type}>
      <CollapsibleTrigger className="group flex w-full items-center gap-2 py-1 text-left">
        <ChevronRight size={12} className="transition-transform group-data-open:rotate-90" />
        <Badge variant="secondary" className="font-mono">{d.type}</Badge>
        <span className="text-muted-foreground text-xs">{d.summary}</span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="border-border ml-2 border-l pl-3">
          {d.children.map((child, i) => (
            <Node key={i} check={child} depth={depth + 1} />
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function CheckTree({ check }: { check: unknown }) {
  return (
    <div data-testid="check-tree">
      <Node check={check} depth={0} />
    </div>
  );
}
