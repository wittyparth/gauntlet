"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { Target } from "@/lib/api/models";

/** Never shows secret values, only the secret's name. */
export function TargetCard({ target }: { target: Target }) {
  return (
    <Card size="sm">
      <CardHeader><CardTitle><h2 className="text-sm font-medium">Target</h2></CardTitle></CardHeader>
      <CardContent className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{target.kind}</Badge>
          {target.wired ? <Badge variant="outline">wired</Badge> : null}
          {target.model ? <span className="font-mono text-xs">{target.model}</span> : null}
          {target.temperature != null ? <span className="text-muted-foreground text-xs">temperature {target.temperature}</span> : null}
        </div>
        {target.base_url ? <div className="font-mono text-xs">{target.base_url}</div> : null}
        {target.url ? <div className="font-mono text-xs">{target.method ?? "POST"} {target.url}{target.reply_path ? ` , reply at ${target.reply_path}` : ""}</div> : null}
        {target.api_key_secret ? <div className="text-muted-foreground text-xs">API key secret: <span className="font-mono">{target.api_key_secret}</span></div> : null}
        {target.system_prompt ? (
          <Collapsible>
            <CollapsibleTrigger render={<Button variant="ghost" size="xs" />}>System prompt</CollapsibleTrigger>
            <CollapsibleContent>
              <pre className="bg-muted/40 mt-1 max-h-60 overflow-auto rounded-md border p-2 font-mono text-xs whitespace-pre-wrap">{target.system_prompt}</pre>
            </CollapsibleContent>
          </Collapsible>
        ) : null}
      </CardContent>
    </Card>
  );
}
