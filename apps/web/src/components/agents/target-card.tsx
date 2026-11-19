"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { Target } from "@/lib/api/models";

/** Never shows secret values, only the secret's name. */
export function TargetCard({ target }: { target: Target }) {
  const wired = target.kind !== "hosted" && target.wired;
  const model = target.kind !== "http" ? target.model : null;
  const temperature = target.kind === "hosted" ? target.temperature : null;
  const baseUrl = target.kind === "openai_compat" ? target.base_url : null;
  const apiKeySecret = target.kind === "openai_compat" ? target.api_key_secret : null;
  const http = target.kind === "http" ? target : null;
  const systemPrompt = target.kind === "hosted" ? target.system_prompt : null;
  return (
    <Card size="sm">
      <CardHeader><CardTitle><h2 className="text-sm font-medium">Target</h2></CardTitle></CardHeader>
      <CardContent className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{target.kind}</Badge>
          {wired ? <Badge variant="outline">wired</Badge> : null}
          {model ? <span className="font-mono text-xs">{model}</span> : null}
          {temperature != null ? <span className="text-muted-foreground text-xs">temperature {temperature}</span> : null}
        </div>
        {baseUrl ? <div className="font-mono text-xs">{baseUrl}</div> : null}
        {http ? <div className="font-mono text-xs">{http.method} {http.url}{http.reply_path ? ` , reply at ${http.reply_path}` : ""}</div> : null}
        {apiKeySecret ? <div className="text-muted-foreground text-xs">API key secret: <span className="font-mono">{apiKeySecret}</span></div> : null}
        {systemPrompt ? (
          <Collapsible>
            <CollapsibleTrigger render={<Button variant="ghost" size="xs" />}>System prompt</CollapsibleTrigger>
            <CollapsibleContent>
              <pre className="bg-muted/40 mt-1 max-h-60 overflow-auto rounded-md border p-2 font-mono text-xs whitespace-pre-wrap">{systemPrompt}</pre>
            </CollapsibleContent>
          </Collapsible>
        ) : null}
      </CardContent>
    </Card>
  );
}
