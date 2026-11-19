"use client";

import { Pause } from "@/components/animate-ui/icons/pause";
import { Play } from "@/components/animate-ui/icons/play";
import { X } from "@/components/animate-ui/icons/x";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { useToast } from "@/components/shared/use-toast";
import { Button } from "@/components/ui/button";
import { useCancelRun, usePauseRun, useResumeRun } from "@/lib/api/hooks/write";
import { isTerminalRun } from "@/lib/api/models";

export function RunControls({ runId, status }: { runId: string; status: string }) {
  const toast = useToast();
  const pause = usePauseRun(runId);
  const resume = useResumeRun(runId);
  const cancel = useCancelRun(runId);
  if (isTerminalRun(status)) return null;
  return (
    <>
      {status === "paused" ? (
        <Button
          size="sm"
          variant="outline"
          disabled={resume.isPending}
          onClick={() => void toast.promise(resume.mutateAsync(), { loading: "Resuming run", success: "Run resumed", error: "Could not resume the run" }).catch(() => {})}
        >
          <Play size={14} /> Resume
        </Button>
      ) : (
        <Button
          size="sm"
          variant="outline"
          disabled={pause.isPending}
          onClick={() => void toast.promise(pause.mutateAsync(), { loading: "Pausing run", success: "Run paused", error: "Could not pause the run" }).catch(() => {})}
        >
          <Pause size={14} /> Pause
        </Button>
      )}
      <ConfirmDialog
        trigger={
          <Button size="sm" variant="outline">
            <X size={14} /> Cancel
          </Button>
        }
        title="Cancel this run?"
        description="Episodes that are queued will not start. Episodes already running finish their current step. Results so far are kept."
        confirmLabel="Cancel run"
        cancelLabel="Keep running"
        onConfirm={() => void toast.promise(cancel.mutateAsync(), { loading: "Cancelling run", success: "Run cancelled", error: "Could not cancel the run" }).catch(() => {})}
      />
    </>
  );
}
