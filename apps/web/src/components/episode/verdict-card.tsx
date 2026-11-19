"use client";

import { Fade } from "@animate-ui/react/primitives/effects/fade";

import { Money } from "@/components/shared/live-number";
import { SeqAnchor } from "@/components/shared/seq-anchor";
import { SeverityBadge, VerdictBadge } from "@/components/shared/badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { Verdict } from "@/lib/api/models";

export function VerdictCard({
  verdict,
  activeEvidence,
  onSelectEvidence,
  animateIn,
}: {
  verdict: Verdict;
  activeEvidence: { seq: number | null; quote: string | null };
  onSelectEvidence: (seq: number, quote: string | null) => void;
  animateIn?: boolean;
}) {
  const v = verdict;
  const card = (
    <Card size="sm" data-testid="verdict-card" data-result={v.result}>
      <CardContent className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <VerdictBadge result={v.result} />
          <span className="font-mono text-sm font-medium">{v.criterion}</span>
          <SeverityBadge severity={v.severity} />
          {v.hard_fail ? <Badge variant="destructive">hard fail</Badge> : null}
        </div>
        <div className="text-muted-foreground flex flex-wrap items-center gap-x-2 text-xs">
          <Badge variant="secondary">{v.stage}</Badge>
          <span className="font-mono">{v.evaluator}</span>
          {v.model ? <span className="font-mono">{v.model}</span> : null}
          {v.confidence != null ? <span>conf {v.confidence.toFixed(2)}</span> : null}
          {v.cost ? <Money usdMicros={v.cost.usd_micros} /> : null}
        </div>
        {v.reasoning ? (
          <Collapsible>
            <CollapsibleTrigger render={<Button variant="ghost" size="xs" className="text-muted-foreground" />}>
              Reasoning
            </CollapsibleTrigger>
            <CollapsibleContent>
              <p className="text-muted-foreground mt-1 text-xs whitespace-pre-wrap">{v.reasoning}</p>
            </CollapsibleContent>
          </Collapsible>
        ) : null}
        {v.evidence.length > 0 ? (
          <div className="flex flex-col gap-1">
            <div className="text-muted-foreground text-xs">Evidence</div>
            {v.evidence.map((ev, i) => {
              const active = activeEvidence.seq === ev.seq && activeEvidence.quote === (ev.quote ?? null);
              return (
                <Button
                  key={`${ev.seq}-${i}`}
                  type="button"
                  variant="ghost"
                  data-testid="evidence-quote"
                  data-seq={ev.seq}
                  aria-pressed={active}
                  onClick={() => onSelectEvidence(ev.seq, ev.quote ?? null)}
                  className="h-auto w-full justify-start gap-2 px-2 py-1 text-left font-normal whitespace-normal aria-pressed:bg-muted"
                >
                  <SeqAnchor seq={ev.seq} onSelect={(s) => onSelectEvidence(s, ev.quote ?? null)} />
                  <span className="min-w-0 flex-1">
                    {ev.quote ? <span>“{ev.quote}”</span> : <span className="text-muted-foreground">event {ev.seq}</span>}
                    {ev.note ? <span className="text-muted-foreground block text-xs">{ev.note}</span> : null}
                  </span>
                </Button>
              );
            })}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
  return animateIn ? <Fade initialOpacity={0}>{card}</Fade> : card;
}
