"use client";

import { useState } from "react";

import { OctagonAlert } from "@/components/animate-ui/icons/octagon-alert";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingCard } from "@/components/shared/loading";
import { useToast } from "@/components/shared/use-toast";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useEngageKillSwitch, useKillSwitch, useReleaseKillSwitch } from "@/lib/api/hooks/security";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

function EngageDialog() {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const engage = useEngageKillSwitch();
  const toast = useToast();
  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger render={<Button variant="destructive" size="sm" />}>
        <OctagonAlert size={14} animateOnHover /> Engage kill switch
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Stop all attack runs?</AlertDialogTitle>
          <AlertDialogDescription>
            Queued attack episodes are cancelled at once and running ones within seconds. New campaigns are refused until
            you release the switch.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="kill-reason">Reason</Label>
          <Input id="kill-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why are you stopping attacks?" />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep running</AlertDialogCancel>
          <Button
            variant="destructive"
            disabled={reason.trim().length === 0 || engage.isPending}
            onClick={() => {
              void toast
                .promise(engage.mutateAsync(reason.trim()), {
                  loading: "Engaging kill switch",
                  success: "Kill switch engaged",
                  error: "Could not engage the kill switch",
                })
                .then(() => {
                  setOpen(false);
                  setReason("");
                })
                .catch(() => undefined);
            }}
          >
            Engage kill switch
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

/** Kill switch state and its control. Engaged state is text plus icon, not colour alone. */
export function KillSwitchCard({ className }: { className?: string }) {
  const q = useKillSwitch();
  const release = useReleaseKillSwitch();
  const toast = useToast();
  if (q.isLoading) return <LoadingCard lines={1} />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const engaged = q.data.engaged;
  return (
    <Card size="sm" className={cn(engaged && "border-destructive/60", className)} data-testid="kill-switch">
      <CardContent className="flex flex-col items-start gap-3 p-3">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-medium whitespace-nowrap">Kill switch</h2>
            {engaged ? (
              <Badge variant="outline" className="border-destructive/40 bg-destructive/10 text-destructive">
                <OctagonAlert size={12} /> Engaged
              </Badge>
            ) : (
              <Badge variant="outline" className="border-success/40 text-success whitespace-nowrap">
                Off: attacks allowed
              </Badge>
            )}
          </div>
          {q.data.switches.map((s) => (
            <p key={s.id} className="text-muted-foreground text-xs">
              {s.scope === "run" ? `Run ${s.run_id}` : "Workspace"}: {s.reason} ({s.engaged_by}, {timeAgo(s.engaged_at)})
            </p>
          ))}
        </div>
        {engaged ? (
          <Button
            variant="outline"
            size="sm"
            disabled={release.isPending}
            onClick={() =>
              void toast
                .promise(release.mutateAsync(), {
                  loading: "Releasing",
                  success: "Kill switch released",
                  error: "Could not release the kill switch",
                })
                .catch(() => undefined)
            }
          >
            Release
          </Button>
        ) : (
          <EngageDialog />
        )}
      </CardContent>
    </Card>
  );
}
