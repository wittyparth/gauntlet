import type { ReactNode } from "react";

import { Card, CardContent } from "@/components/ui/card";

export function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon?: ReactNode;
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <Card className="border-dashed" data-testid="empty-state">
      <CardContent className="flex flex-col items-start gap-2 p-4">
        {icon ? <div className="text-muted-foreground">{icon}</div> : null}
        <h2 className="text-sm font-medium">{title}</h2>
        {body ? <p className="text-muted-foreground max-w-prose text-sm">{body}</p> : null}
        {action ? <div className="pt-1">{action}</div> : null}
      </CardContent>
    </Card>
  );
}
