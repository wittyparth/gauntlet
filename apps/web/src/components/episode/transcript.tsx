"use client";

import { Highlight } from "@animate-ui/react/primitives/effects/highlight";
import { ScrollFade } from "@animate-ui/react/primitives/effects/scroll-fade";
import { useEffect, useRef, useState } from "react";

import { ChevronDown } from "@/components/animate-ui/icons/chevron-down";
import { LiveStatusText } from "@/components/shared/live-status-text";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { EpisodeEvent } from "@/lib/api/models";

import { isMessage } from "./payloads";
import { TranscriptRow } from "./transcript-row";

export type TranscriptMode = "messages" | "all";

export function Transcript({
  events,
  selectedSeq = null,
  quote = null,
  onSelect,
  tools = {},
  live = false,
  compact = false,
  mode,
  onModeChange,
  onOpenState,
  followBottom = false,
}: {
  events: EpisodeEvent[];
  selectedSeq?: number | null;
  quote?: string | null;
  onSelect: (seq: number) => void;
  tools?: Record<string, string>;
  live?: boolean;
  compact?: boolean;
  mode: TranscriptMode;
  onModeChange?: (m: TranscriptMode) => void;
  onOpenState?: (seq: number) => void;
  followBottom?: boolean;
}) {
  const shown = mode === "messages" ? events.filter(isMessage) : events;
  const seen = useRef<Set<number> | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);

  // Rows already present on first paint never animate; later arrivals do.
  const firstPaint = seen.current === null;
  if (firstPaint) seen.current = new Set(events.map((e) => e.seq));
  const arriving = new Set(events.filter((e) => !seen.current?.has(e.seq)).map((e) => e.seq));
  useEffect(() => {
    events.forEach((e) => seen.current?.add(e.seq));
  });

  useEffect(() => {
    const el = scroller.current;
    if (followBottom && atBottom && el) el.scrollTop = el.scrollHeight;
  }, [events.length, followBottom, atBottom]);

  const lastTool = (name: string) => tools[name];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {onModeChange ? (
        <div className="flex items-center justify-between border-b px-3 py-2">
          <h2 className="text-sm font-medium">Transcript</h2>
          <ToggleGroup
            value={[mode]}
            onValueChange={(v) => v[0] && onModeChange(v[0] as TranscriptMode)}
            variant="outline"
            size="sm"
            aria-label="Transcript view"
          >
            <ToggleGroupItem value="messages">Messages</ToggleGroupItem>
            <ToggleGroupItem value="all">All events</ToggleGroupItem>
          </ToggleGroup>
        </div>
      ) : null}
      <ScrollFade
        ref={scroller}
        className="relative min-h-0 flex-1 overflow-y-auto p-2"
        onScroll={(e) => {
          const el = e.currentTarget;
          setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 24);
        }}
      >
        <Highlight
          controlledItems
          mode="parent"
          value={selectedSeq == null ? null : String(selectedSeq)}
          hover={false}
          click={false}
          className="bg-muted rounded-md"
          containerClassName="flex flex-col gap-0.5"
        >
          {shown.map((e) => (
            <TranscriptRow
              key={e.seq}
              event={e}
              selected={selectedSeq === e.seq}
              quote={quote}
              risk={e.kind === "tool_call" ? lastTool(String(e.payload.tool ?? "")) : undefined}
              onSelect={onSelect}
              animateIn={!firstPaint && arriving.has(e.seq)}
              compact={compact}
              onOpenState={onOpenState}
            />
          ))}
        </Highlight>
        {live ? (
          <div className="px-2 py-2">
            <LiveStatusText text="Agent is replying…" className="text-muted-foreground text-xs" />
          </div>
        ) : null}
      </ScrollFade>
      {followBottom && !atBottom ? (
        <div className="flex justify-center border-t p-1">
          <Button
            size="xs"
            variant="outline"
            onClick={() => {
              const el = scroller.current;
              if (el) el.scrollTop = el.scrollHeight;
              setAtBottom(true);
            }}
          >
            <ChevronDown size={12} /> Jump to latest
          </Button>
        </div>
      ) : null}
    </div>
  );
}
