"use client";

import { CircleAlert } from "@/components/animate-ui/icons/circle-alert";
import { RefreshCw } from "@/components/animate-ui/icons/refresh-cw";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { toApiError } from "@/lib/api/errors";

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const e = toApiError(error);
  return (
    <Card className="border-destructive/50" role="alert" data-testid="error-state">
      <CardContent className="flex flex-col items-start gap-2 p-4">
        <div className="text-destructive flex items-center gap-2 font-medium">
          <CircleAlert size={16} animate /> Could not load this
        </div>
        <p className="text-sm">{e.message}</p>
        <div className="flex items-center gap-2">
          {onRetry ? (
            <Button size="sm" variant="outline" onClick={onRetry}>
              <RefreshCw size={14} animateOnHover /> Retry
            </Button>
          ) : null}
          <Collapsible>
            <CollapsibleTrigger render={<Button size="sm" variant="ghost" />}>Details</CollapsibleTrigger>
            <CollapsibleContent>
              <pre className="text-muted-foreground mt-2 font-mono text-xs whitespace-pre-wrap">
                {`code: ${e.code}\nstatus: ${e.status}\nmessage: ${e.message}${
                  e.detail ? `\ndetail: ${JSON.stringify(e.detail)}` : ""
                }`}
              </pre>
            </CollapsibleContent>
          </Collapsible>
        </div>
      </CardContent>
    </Card>
  );
}

/** 404 on a detail page. */
export function isNotFound(error: unknown) {
  return toApiError(error).status === 404;
}
