"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useRunList } from "@/lib/api/hooks/read";
import { timeAgo } from "@/lib/format";

/** Pick a finished run on the same suite, then open the comparison. */
export function BaselinePicker({ runId, suiteId, label = "Compare", variant = "outline" }: { runId: string; suiteId: string; label?: string; variant?: "outline" | "default" }) {
  const router = useRouter();
  const runs = useRunList();
  const [baseline, setBaseline] = useState<string | null>(null);
  const options = (runs.data?.items ?? []).filter((r) => r.suite_id === suiteId && r.id !== runId && r.status === "done");
  return (
    <Dialog>
      <DialogTrigger render={<Button size="sm" variant={variant} />}>{label}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Compare with a baseline run</DialogTitle>
          <DialogDescription>Only finished runs of the same suite can be compared.</DialogDescription>
        </DialogHeader>
        {options.length === 0 ? (
          <p className="text-muted-foreground text-sm" data-testid="no-baselines">No other finished run of this suite yet.</p>
        ) : (
          <Select items={options.map((r) => ({ value: r.id, label: `${r.id} (${timeAgo(r.created_at)})` }))} value={baseline} onValueChange={(v) => setBaseline(v)}>
            <SelectTrigger aria-label="Baseline run" className="w-full"><SelectValue placeholder="Choose a baseline run" /></SelectTrigger>
            <SelectContent>
              {options.map((r) => <SelectItem key={r.id} value={r.id}>{r.id} ({timeAgo(r.created_at)})</SelectItem>)}
            </SelectContent>
          </Select>
        )}
        <DialogFooter>
          <Button disabled={!baseline} onClick={() => baseline && router.push(`/runs/${runId}/compare?baseline=${baseline}`)}>Compare</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
