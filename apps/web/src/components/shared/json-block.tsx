"use client";

import { CopyButton, CopyButtonIcon } from "@animate-ui/react/primitives/buttons/copy";
import { useState } from "react";

import { CircleCheck } from "@/components/animate-ui/icons/circle-check";
import { Copy } from "@/components/animate-ui/icons/copy";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

const COLLAPSE_ABOVE_LINES = 12;

/** Pretty JSON in a bounded scroll area; collapsed above 12 lines. No highlighting dependency. */
export function JsonBlock({
  value,
  label = "JSON",
  className,
  maxHeight = 240,
  defaultOpen,
}: {
  value: unknown;
  label?: string;
  className?: string;
  maxHeight?: number;
  defaultOpen?: boolean;
}) {
  const text = typeof value === "string" ? value : (JSON.stringify(value, null, 2) ?? "null");
  const lines = text.split("\n").length;
  const [open, setOpen] = useState(defaultOpen ?? lines <= COLLAPSE_ABOVE_LINES);
  return (
    <Collapsible open={open} onOpenChange={setOpen} className={cn("min-w-0", className)}>
      <div className="flex items-center gap-1">
        <CollapsibleTrigger
          render={<Button variant="ghost" size="xs" className="text-muted-foreground" />}
        >
          {open ? "Hide" : "Show"} {label}
          <span className="font-mono">({lines} {lines === 1 ? "line" : "lines"})</span>
        </CollapsibleTrigger>
        <CopyButton asChild content={text} delay={1500}>
          <Button variant="ghost" size="icon-xs" aria-label={`Copy ${label}`}>
            <CopyButtonIcon icon={<Copy size={12} />} copiedIcon={<CircleCheck size={12} animate />} />
          </Button>
        </CopyButton>
      </div>
      <CollapsibleContent>
        <ScrollArea className="bg-muted/40 mt-1 rounded-md border" style={{ maxHeight }}>
          <pre className="p-2 font-mono text-xs whitespace-pre-wrap break-all" style={{ maxHeight }}>
            {text}
          </pre>
        </ScrollArea>
      </CollapsibleContent>
    </Collapsible>
  );
}
