"use client";

import { useState } from "react";

import { Play } from "@/components/animate-ui/icons/play";
import { RunConfigForm } from "@/components/shared/run-config-form";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export function StartRunDialog({ agentVersionId, variant = "default" }: { agentVersionId: string; variant?: "default" | "outline" }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" variant={variant} />}>
        <Play size={14} animateOnHover /> Start run
      </DialogTrigger>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Start a run</DialogTitle>
          <DialogDescription>Pick a suite and a budget. Nothing starts until you confirm.</DialogDescription>
        </DialogHeader>
        {open ? <RunConfigForm agentVersionId={agentVersionId} /> : null}
      </DialogContent>
    </Dialog>
  );
}
