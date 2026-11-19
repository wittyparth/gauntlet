"use client";

import { HighlightText } from "@animate-ui/react/primitives/texts/highlight";
import { Fade } from "@animate-ui/react/primitives/effects/fade";
import { HighlightItem } from "@animate-ui/react/primitives/effects/highlight";

import { CircleCheck } from "@/components/animate-ui/icons/circle-check";
import { CircleX } from "@/components/animate-ui/icons/circle-x";
import { TriangleAlert } from "@/components/animate-ui/icons/triangle-alert";
import { JsonBlock } from "@/components/shared/json-block";
import { RiskBadge } from "@/components/shared/badges";
import { SeqAnchor } from "@/components/shared/seq-anchor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { EpisodeEvent } from "@/lib/api/models";
import { formatDuration, formatUsd } from "@/lib/format";
import { cn } from "@/lib/utils";

import { endedInfo, faultInfo, messageText, summarize, toolCall, toolResult } from "./payloads";
import { findQuote } from "./quote-match";

const ACTOR_LABEL: Record<string, string> = { user: "user", agent: "agent", tool: "tool", platform: "platform" };

function MessageBody({ text, quote }: { text: string; quote: string | null }) {
  const m = findQuote(text, quote);
  if (!m) return <p className="whitespace-pre-wrap">{text}</p>;
  return (
    <p className="whitespace-pre-wrap">
      {text.slice(0, m.start)}
      <mark data-testid="evidence-match" className="rounded-sm bg-transparent text-inherit">
        <HighlightText text={text.slice(m.start, m.end)} transition={{ duration: 0.4 }} className="bg-linear-to-r from-warning/40 to-warning/40" />
      </mark>
      {text.slice(m.end)}
    </p>
  );
}

function ToolCallBody({ e, risk, onOpenState }: { e: EpisodeEvent; risk?: string; onOpenState?: (seq: number) => void }) {
  void onOpenState;
  const c = toolCall(e);
  const preview = JSON.stringify(c.args ?? {});
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="text-muted-foreground">→</span>
        <span className="font-mono font-medium">{c.tool}</span>
        {risk ? <RiskBadge risk={risk} /> : null}
        {c.via ? <Badge variant="outline">{c.via}</Badge> : null}
        <span className="text-muted-foreground truncate font-mono text-xs">{preview}</span>
      </div>
      <JsonBlock value={c.args ?? {}} label="args" defaultOpen={false} />
    </div>
  );
}

function ToolResultBody({ e, onOpenState }: { e: EpisodeEvent; onOpenState?: (seq: number) => void }) {
  const r = toolResult(e);
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground">←</span>
        {r.ok ? (
          <span className="text-success inline-flex items-center gap-1">
            <CircleCheck size={14} /> ok
          </span>
        ) : (
          <span className="text-destructive inline-flex items-center gap-1">
            <CircleX size={14} /> error{r.error ? `: ${r.error}` : ""}
          </span>
        )}
        <span className="text-muted-foreground font-mono text-xs">{formatDuration(e.wall_ms)}</span>
        {r.patch.length > 0 ? (
          <Button
            variant="outline"
            size="xs"
            onClick={(ev) => {
              ev.stopPropagation();
              onOpenState?.(e.seq);
            }}
          >
            {r.patch.length} change{r.patch.length === 1 ? "" : "s"}
          </Button>
        ) : null}
      </div>
      {r.result !== undefined && r.result !== null ? <JsonBlock value={r.result} label="result" defaultOpen={false} /> : null}
    </div>
  );
}

function RowBody({
  e,
  quote,
  risk,
  onOpenState,
}: {
  e: EpisodeEvent;
  quote: string | null;
  risk?: string;
  onOpenState?: (seq: number) => void;
}) {
  switch (e.kind) {
    case "user_message":
    case "agent_message":
      return <MessageBody text={messageText(e)} quote={quote} />;
    case "tool_call":
      return <ToolCallBody e={e} risk={risk} />;
    case "tool_result":
      return <ToolResultBody e={e} onOpenState={onOpenState} />;
    case "fault_injected": {
      const f = faultInfo(e);
      return (
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="border-warning/40 text-warning">
            <TriangleAlert size={12} /> fault
          </Badge>
          <span className="font-mono text-xs">
            {f.kind}
            {f.tool ? ` on ${f.tool}` : ""}
          </span>
        </div>
      );
    }
    case "episode_ended": {
      const i = endedInfo(e);
      return (
        <div className="flex flex-col gap-1">
          <span className="text-muted-foreground">
            Ended: {i.outcome} ({i.termination}){i.detail ? `, ${i.detail}` : ""}
          </span>
          <JsonBlock value={e.payload} label="payload" defaultOpen={false} />
        </div>
      );
    }
    default:
      return (
        <div className="flex flex-col gap-1">
          <span className="text-muted-foreground">{summarize(e)}</span>
          <JsonBlock value={e.payload} label="payload" defaultOpen={false} />
        </div>
      );
  }
}

function costTip(e: EpisodeEvent): string | null {
  if (!e.cost) return null;
  const parts = [`${formatUsd(e.cost.usd_micros)}`, `${e.cost.input_tokens} in / ${e.cost.output_tokens} out tokens`];
  if (e.cost.model) parts.push(e.cost.model);
  return parts.join(" · ");
}

export function TranscriptRow({
  event,
  selected,
  quote,
  risk,
  onSelect,
  animateIn,
  compact,
  onOpenState,
}: {
  event: EpisodeEvent;
  selected: boolean;
  quote: string | null;
  risk?: string;
  onSelect: (seq: number) => void;
  animateIn?: boolean;
  compact?: boolean;
  onOpenState?: (seq: number) => void;
}) {
  const tip = costTip(event);
  const untrusted = event.origin?.trust === "untrusted_external";
  const row = (
    <HighlightItem value={String(event.seq)} className="rounded-md">
      <div
        id={`e-${event.seq}`}
        data-testid={`event-${event.seq}`}
        data-selected={selected ? "true" : undefined}
        data-kind={event.kind}
        onClick={() => onSelect(event.seq)}
        className={cn(
          "grid cursor-pointer grid-cols-[auto_4.5rem_1fr_auto] items-start gap-x-2 rounded-md px-2 py-1.5",
          compact && "py-1",
        )}
      >
        <SeqAnchor seq={event.seq} onSelect={onSelect} />
        <Badge variant="secondary" className="justify-self-start font-mono text-[11px]">
          {ACTOR_LABEL[event.actor] ?? event.actor}
        </Badge>
        <div className="min-w-0 break-words">
          <RowBody e={event} quote={selected ? quote : null} risk={risk} onOpenState={onOpenState} />
        </div>
        <div className="flex items-center gap-1">
          {untrusted ? (
            <Tooltip>
              <TooltipTrigger render={<Badge variant="outline" />}>untrusted</TooltipTrigger>
              <TooltipContent>
                {event.origin?.source ?? "external"}
                {event.origin?.markers.length ? ` · ${event.origin.markers.join(", ")}` : ""}
              </TooltipContent>
            </Tooltip>
          ) : null}
          {tip ? (
            <Tooltip>
              <TooltipTrigger render={<span className="text-muted-foreground font-mono text-[11px]" />}>
                {formatUsd(event.cost?.usd_micros ?? 0)}
              </TooltipTrigger>
              <TooltipContent>{tip}</TooltipContent>
            </Tooltip>
          ) : null}
        </div>
      </div>
    </HighlightItem>
  );
  return animateIn ? <Fade initialOpacity={0} transition={{ duration: 0.25 }}>{row}</Fade> : row;
}
