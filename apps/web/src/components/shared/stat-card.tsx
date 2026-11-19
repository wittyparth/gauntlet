import type { ReactNode } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export function StatCard({
  name,
  label,
  value,
  hint,
  interval,
  children,
}: {
  name: string;
  label: string;
  value: ReactNode;
  hint?: string;
  interval?: string;
  children?: ReactNode;
}) {
  const body = (
    <Card data-testid={`stat-${name}`} size="sm">
      <CardContent className="flex flex-col gap-1 p-3">
        <div className="text-muted-foreground text-xs">{label}</div>
        <div className="text-xl leading-tight font-semibold">{value}</div>
        {interval ? <div className="text-muted-foreground font-mono text-xs">{interval}</div> : null}
        {children}
      </CardContent>
    </Card>
  );
  if (!hint) return body;
  return (
    <Tooltip>
      <TooltipTrigger render={<div />}>{body}</TooltipTrigger>
      <TooltipContent>{hint}</TooltipContent>
    </Tooltip>
  );
}
