"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** `[12]`: selects event 12 through the page's selection handler. */
export function SeqAnchor({
  seq,
  onSelect,
  className,
}: {
  seq: number;
  onSelect: (seq: number) => void;
  className?: string;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="xs"
      aria-label={`Go to event ${seq}`}
      className={cn("text-muted-foreground h-5 px-1 font-mono text-xs", className)}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(seq);
      }}
    >
      [{seq}]
    </Button>
  );
}
