"use client";

import { CopyButton, CopyButtonIcon } from "@animate-ui/react/primitives/buttons/copy";

import { Copy } from "@/components/animate-ui/icons/copy";
import { CircleCheck } from "@/components/animate-ui/icons/circle-check";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { shortId } from "@/lib/format";

/** Short prefixed id; the button copies the full id. */
export function CopyId({ id }: { id: string }) {
  return (
    <span className="inline-flex items-center gap-1 font-mono text-xs">
      <span title={id}>{shortId(id)}</span>
      <Tooltip>
        <TooltipTrigger
          render={
            <CopyButton asChild content={id} delay={1500}>
              <Button variant="ghost" size="icon-xs" aria-label={`Copy ${id}`}>
                <CopyButtonIcon icon={<Copy size={12} />} copiedIcon={<CircleCheck size={12} animate />} />
              </Button>
            </CopyButton>
          }
        />
        <TooltipContent>Copy id</TooltipContent>
      </Tooltip>
    </span>
  );
}
