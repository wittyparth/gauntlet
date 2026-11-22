"use client";

import { useState } from "react";

import { SeverityBadge } from "@/components/shared/badges";
import { JsonBlock } from "@/components/shared/json-block";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import type { Approval } from "@/lib/api/hooks/approvals";
import { timeAgo } from "@/lib/format";

/** Approve and Deny carry equal weight; Deny can carry a reason. */
export function ApprovalCard({ approval, busy, onDecide }: { approval: Approval; busy: boolean; onDecide: (decision: "approve" | "deny", note?: string) => void }) {
  const [note, setNote] = useState("");
  const [open, setOpen] = useState(false);
  const d = approval.decision;
  return (
    <Card data-testid="approval-card" className="animate-in fade-in duration-300">
      <CardContent className="flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm">{d.tool ?? d.kind}</span>
          {d.rule_id ? <span className="text-muted-foreground text-xs">rule <span className="font-mono">{d.rule_id}</span></span> : null}
          {d.severity ? <SeverityBadge severity={d.severity} /> : null}
        </div>
        {d.message ? <p className="text-sm">{d.message}</p> : null}
        <JsonBlock value={d.args ?? {}} label="arguments" defaultOpen />
        <p className="text-muted-foreground text-xs">
          requested {timeAgo(approval.requested_at)}
          {d.agent_id ? ` · agent ${d.agent_id}` : ""} · session {d.session_id} · expires {new Date(approval.expires_at).toLocaleString()}
        </p>
        <div className="flex justify-end gap-2">
          <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger render={<Button variant="outline" disabled={busy} />}>Deny</PopoverTrigger>
            <PopoverContent className="flex w-72 flex-col gap-2">
              <label className="text-xs" htmlFor={`deny-${approval.id}`}>Reason (optional)</label>
              <Textarea id={`deny-${approval.id}`} rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
              <Button variant="destructive" size="sm" disabled={busy} onClick={() => { setOpen(false); onDecide("deny", note); }}>Deny this action</Button>
            </PopoverContent>
          </Popover>
          <Button variant="outline" disabled={busy} onClick={() => onDecide("approve")}>Approve</Button>
        </div>
      </CardContent>
    </Card>
  );
}
