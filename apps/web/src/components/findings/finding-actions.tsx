"use client";

import { useRouter } from "next/navigation";

import { Download } from "@/components/animate-ui/icons/download";
import { Ellipsis } from "@/components/animate-ui/icons/ellipsis";
import { useToast } from "@/components/shared/use-toast";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useExportFinding, useFindingRun, usePinFinding, type ExportFormat } from "@/lib/api/hooks/findings";

const EXPORTS: { format: ExportFormat; label: string }[] = [
  { format: "md", label: "Markdown report" },
  { format: "json", label: "JSON" },
  { format: "sarif", label: "SARIF" },
];

/** Replay, verify, pin and export. Replay and verify start a run and open its console. */
export function FindingActions({ findingId }: { findingId: string }) {
  const router = useRouter();
  const toast = useToast();
  const replay = useFindingRun(findingId, "replay");
  const verify = useFindingRun(findingId, "verify");
  const pin = usePinFinding(findingId);
  const exportFinding = useExportFinding(findingId);

  const startRun = async (kind: "replay" | "verify") => {
    const m = kind === "replay" ? replay : verify;
    try {
      const run = await m.mutateAsync();
      toast.success(kind === "replay" ? "Replay started" : "Verification started", run.id);
      router.push(`/runs/${run.id}`);
    } catch (e) {
      toast.error(e, kind === "replay" ? "Could not start the replay" : "Could not start the verification");
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="outline" size="sm" aria-label="Finding actions" />}>
        <Ellipsis size={14} animateOnHover /> Actions
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuGroup>
          <DropdownMenuLabel>Reproduce</DropdownMenuLabel>
          <DropdownMenuItem onClick={() => void startRun("replay")}>Replay (5 attempts)</DropdownMenuItem>
          <DropdownMenuItem onClick={() => void startRun("verify")}>Verify the fix</DropdownMenuItem>
          <DropdownMenuItem
            onClick={() =>
              void toast
                .promise(pin.mutateAsync(), {
                  loading: "Pinning scenario",
                  success: "Pinned to the security-regression suite",
                  error: "Could not pin",
                })
                .catch(() => undefined)
            }
          >
            Pin as regression scenario
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuLabel>Export</DropdownMenuLabel>
          {EXPORTS.map((x) => (
            <DropdownMenuItem
              key={x.format}
              onClick={() =>
                void toast
                  .promise(exportFinding.mutateAsync(x.format), {
                    loading: "Preparing export",
                    success: `${x.label} downloaded`,
                    error: "Export failed",
                  })
                  .catch(() => undefined)
              }
            >
              <Download size={14} /> {x.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
