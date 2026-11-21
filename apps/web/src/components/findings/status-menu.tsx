"use client";

import { ChevronDown } from "@/components/animate-ui/icons/chevron-down";
import { useToast } from "@/components/shared/use-toast";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useUpdateFindingStatus } from "@/lib/api/hooks/findings";

import { STATUSES, statusLabel } from "./finding-utils";

/** Radio menu of every status; the server rejects illegal transitions and the toast says why. */
export function StatusMenu({ findingId, status }: { findingId: string; status: string }) {
  const update = useUpdateFindingStatus(findingId);
  const toast = useToast();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button variant="outline" size="sm" aria-label={`Status: ${statusLabel(status)}`} data-testid="status-menu" />
        }
      >
        {statusLabel(status)}
        <ChevronDown size={14} animateOnHover />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44">
        <DropdownMenuGroup>
          <DropdownMenuLabel>Move to</DropdownMenuLabel>
          <DropdownMenuRadioGroup
            value={status}
            onValueChange={(next) => {
              if (next === status) return;
              void toast
                .promise(update.mutateAsync({ status: next }), {
                  loading: "Updating status",
                  success: `Marked ${statusLabel(next).toLowerCase()}`,
                  error: "Status change rejected",
                })
                .catch(() => undefined);
            }}
          >
            {STATUSES.map((s) => (
              <DropdownMenuRadioItem key={s.value} value={s.value}>
                {s.label}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
