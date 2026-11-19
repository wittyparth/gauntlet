"use client";

import { CircleCheck } from "@/components/animate-ui/icons/circle-check";
import { CircleX } from "@/components/animate-ui/icons/circle-x";
import { Clock } from "@/components/animate-ui/icons/clock";
import { TriangleAlert } from "@/components/animate-ui/icons/triangle-alert";
import { RiskBadge } from "@/components/shared/badges";
import { EmptyState } from "@/components/shared/empty-state";
import { JsonBlock } from "@/components/shared/json-block";
import { SeqAnchor } from "@/components/shared/seq-anchor";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import type { EpisodeEvent } from "@/lib/api/models";
import { formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

import { faultInfo, toolCall, toolResult } from "./payloads";

type Item =
  | { type: "call"; call: EpisodeEvent; result: EpisodeEvent | null }
  | { type: "fault"; event: EpisodeEvent };

/** Pair `tool_call` with `tool_result` on `payload.call_id`; faults sit between items. */
export function buildTimeline(events: EpisodeEvent[]): Item[] {
  const results = new Map<string, EpisodeEvent>();
  for (const e of events) if (e.kind === "tool_result") results.set(toolResult(e).callId ?? `seq-${e.seq}`, e);
  const items: Item[] = [];
  for (const e of events) {
    if (e.kind === "tool_call") items.push({ type: "call", call: e, result: results.get(toolCall(e).callId ?? "") ?? null });
    else if (e.kind === "fault_injected") items.push({ type: "fault", event: e });
  }
  return items;
}

export function ToolTimeline({
  events,
  tools,
  selectedSeq,
  onSelect,
}: {
  events: EpisodeEvent[];
  tools: Record<string, string>;
  selectedSeq: number | null;
  onSelect: (seq: number) => void;
}) {
  const items = buildTimeline(events);
  if (items.length === 0) {
    return <EmptyState title="No tool calls" body="The agent did not call any tools in this episode." />;
  }
  const maxMs = Math.max(1, ...items.map((i) => (i.type === "call" ? (i.result?.wall_ms ?? 0) : 0)));
  return (
    <div className="flex flex-col gap-1">
      <Accordion multiple className="gap-1">
        {items.map((item) => {
          if (item.type === "fault") {
            const f = faultInfo(item.event);
            return (
              <div
                key={`f-${item.event.seq}`}
                className="border-warning/40 text-warning flex items-center gap-2 rounded-md border px-2 py-1 text-xs"
              >
                <TriangleAlert size={12} /> fault <span className="font-mono">{f.kind}</span>
                {f.tool ? <span className="font-mono">on {f.tool}</span> : null}
                <SeqAnchor seq={item.event.seq} onSelect={onSelect} className="ml-auto" />
              </div>
            );
          }
          const c = toolCall(item.call);
          const r = item.result ? toolResult(item.result) : null;
          const related = selectedSeq === item.call.seq || selectedSeq === item.result?.seq;
          return (
            <AccordionItem
              key={item.call.seq}
              value={String(item.call.seq)}
              data-testid={`timeline-item-${item.call.seq}`}
              data-related={related ? "true" : undefined}
              className={cn("rounded-md border px-2", related && "border-l-ring border-l-2")}
            >
              <AccordionTrigger className="items-center gap-2">
                <span className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
                  <span className="text-muted-foreground w-12 font-mono text-xs">
                    {item.result ? formatDuration(item.result.wall_ms) : "…"}
                  </span>
                  <span className="font-mono">{c.tool}</span>
                  {tools[c.tool] ? <RiskBadge risk={tools[c.tool]} /> : null}
                  {r == null ? (
                    <Badge variant="outline"><Clock size={12} /> pending</Badge>
                  ) : r.ok ? (
                    <span className="text-success inline-flex items-center gap-1 text-xs"><CircleCheck size={12} /> ok</span>
                  ) : (
                    <span className="text-destructive inline-flex items-center gap-1 text-xs"><CircleX size={12} /> error</span>
                  )}
                </span>
              </AccordionTrigger>
              <div className="flex items-center gap-1 pb-2">
                <SeqAnchor seq={item.call.seq} onSelect={onSelect} />
                {item.result ? <SeqAnchor seq={item.result.seq} onSelect={onSelect} /> : null}
                <Progress
                  value={item.result ? ((item.result.wall_ms || 0) / maxMs) * 100 : 0}
                  className="ml-2 w-24"
                  aria-label="Relative duration"
                />
              </div>
              <AccordionContent>
                <div className="flex flex-col gap-2">
                  <JsonBlock value={c.args ?? {}} label="args" />
                  {r?.error ? <p className="text-destructive text-xs">{r.error}</p> : null}
                  {r && r.result != null ? <JsonBlock value={r.result} label="result" /> : null}
                  {r && r.patch.length > 0 ? <JsonBlock value={r.patch} label={`patch (${r.patch.length})`} /> : null}
                </div>
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>
    </div>
  );
}
