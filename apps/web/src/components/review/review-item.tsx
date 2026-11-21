"use client";

import { VerdictBadge } from "@/components/shared/badges";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingCard } from "@/components/shared/loading";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { ReviewItem as Item } from "@/lib/api/hooks/review";

/** The rubric question, the recorded trajectory, and the judge's prediction (hidden until asked). */
export function ReviewItem({
  item,
  loading,
  error,
  revealed,
  onRetry,
}: {
  item: Item | undefined;
  loading: boolean;
  error: unknown;
  revealed: boolean;
  onRetry: () => void;
}) {
  if (loading) return <LoadingCard lines={6} />;
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (!item) return null;
  const r = item.rubric;
  return (
    <div className="flex flex-col gap-3" data-testid="review-item">
      <Card size="sm">
        <CardHeader>
          <CardTitle className="text-sm">{r.question}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <p className="text-muted-foreground text-xs">Scenario: {item.scenario_title}. Goal: {item.goal}</p>
          <Collapsible>
            <CollapsibleTrigger className="text-xs underline">Definitions</CollapsibleTrigger>
            <CollapsibleContent>
              <dl className="mt-2 grid gap-1 text-sm">
                <div><dt className="inline font-medium">Pass: </dt><dd className="inline">{r.pass_definition}</dd></div>
                <div><dt className="inline font-medium">Fail: </dt><dd className="inline">{r.fail_definition}</dd></div>
                {r.na_definition ? <div><dt className="inline font-medium">N/A: </dt><dd className="inline">{r.na_definition}</dd></div> : null}
              </dl>
            </CollapsibleContent>
          </Collapsible>
          {item.my_label ? <Badge variant="outline" className="w-fit">Your label: {item.my_label}</Badge> : null}
        </CardContent>
      </Card>
      <Card size="sm">
        <CardContent>
          <ScrollArea className="h-80">
            <pre className="font-mono text-xs break-words whitespace-pre-wrap" data-testid="review-transcript">{item.transcript}</pre>
          </ScrollArea>
        </CardContent>
      </Card>
      <Card size="sm" data-testid="judge-prediction">
        <CardContent className="text-sm">
          {revealed && item.judge ? (
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2">Judge prediction: <VerdictBadge result={item.judge.result} /></div>
              <p className="text-muted-foreground text-xs">{item.judge.reasoning}</p>
            </div>
          ) : revealed ? (
            <span className="text-muted-foreground">No judge verdict is stored for this item.</span>
          ) : (
            <span className="text-muted-foreground">Judge prediction: hidden. Press h to show it.</span>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
