import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import { statusLabel } from "./finding-utils";

/** Status is text, never colour alone. Verified is the only positive state. */
export function FindingStatusBadge({ status }: { status: string }) {
  const tone =
    status === "verified" || status === "fixed"
      ? "border-success/40 text-success"
      : status === "open"
        ? "border-foreground/30 text-foreground"
        : "text-muted-foreground";
  return (
    <Badge variant="outline" className={cn(tone)} data-testid="finding-status">
      {statusLabel(status)}
    </Badge>
  );
}
