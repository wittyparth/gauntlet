"use client";

import { Plus } from "@/components/animate-ui/icons/plus";
import { RefreshCw } from "@/components/animate-ui/icons/refresh-cw";
import { X } from "@/components/animate-ui/icons/x";
import { EmptyState } from "@/components/shared/empty-state";
import { JsonBlock } from "@/components/shared/json-block";
import { SeqAnchor } from "@/components/shared/seq-anchor";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import type { DiffEntry, DiffView } from "./diff-entries";

const show = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v));

function Entry({ entry, related, onSelect }: { entry: DiffEntry; related: boolean; onSelect: (seq: number) => void }) {
  const Icon = entry.kind === "added" ? Plus : entry.kind === "removed" ? X : RefreshCw;
  const tone = entry.kind === "added" ? "text-success" : entry.kind === "removed" ? "text-destructive" : "text-info";
  return (
    <li
      data-testid="diff-entry"
      data-related={related ? "true" : undefined}
      className={cn("flex flex-col gap-1 border-l-2 border-transparent py-1 pl-2", related && "border-l-ring")}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className={tone}><Icon size={12} /></span>
        <span className="sr-only">{entry.kind}</span>
        <span className="font-mono text-xs">{entry.id}</span>
        {entry.seq >= 0 ? <SeqAnchor seq={entry.seq} onSelect={onSelect} className="ml-auto" /> : null}
      </div>
      {entry.kind === "changed" && entry.changes ? (
        <ul className="flex flex-col gap-0.5 pl-5 font-mono text-xs">
          {entry.changes.map((c) => (
            <li key={c.path}>
              <span className="text-muted-foreground">{c.path}: </span>
              <span className="text-muted-foreground line-through">{show(c.before)}</span>
              {" → "}
              <span>{show(c.after)}</span>
            </li>
          ))}
        </ul>
      ) : entry.record !== undefined && entry.record !== null ? (
        <div className="pl-5"><JsonBlock value={entry.record} label="record" /></div>
      ) : null}
    </li>
  );
}

export function StateDiff({
  view,
  hasToolEvents,
  selectedSeq,
  onSelect,
}: {
  view: DiffView;
  hasToolEvents: boolean;
  selectedSeq: number | null;
  onSelect: (seq: number) => void;
}) {
  if (view.entries.length === 0) {
    return (
      <EmptyState
        title="The agent changed nothing in the world."
        body={hasToolEvents ? undefined : "No world state for this target type."}
      />
    );
  }
  return (
    <Accordion multiple defaultValue={view.groups.map((g) => g.collection)} className="gap-2">
      {view.groups.map((g) => (
        <AccordionItem key={g.collection} value={g.collection} className="rounded-md border px-2">
          <AccordionTrigger className="items-center">
            <span className="flex items-center gap-2">
              <span className="font-mono">{g.collection}</span>
              {g.added ? <Badge variant="outline" className="text-success">+{g.added}</Badge> : null}
              {g.removed ? <Badge variant="outline" className="text-destructive">−{g.removed}</Badge> : null}
              {g.changed ? <Badge variant="outline" className="text-info">~{g.changed}</Badge> : null}
            </span>
          </AccordionTrigger>
          <AccordionContent>
            <ul className="flex flex-col">
              {g.entries.map((e, i) => (
                <Entry key={`${e.id}-${e.seq}-${i}`} entry={e} related={selectedSeq === e.seq} onSelect={onSelect} />
              ))}
            </ul>
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  );
}
