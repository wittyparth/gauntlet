"use client";

import { useState } from "react";

import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { PolicyTestReport } from "@/lib/api/hooks/policies";

import { confirmSummary, needsConfirm, type FailMode, type Mode } from "./mode-logic";

type Next = { mode: Mode; fail: FailMode };

/** Shadow or enforce, and fail open or closed. Risky switches pass through a confirmation that shows the test numbers. */
export function ModeControl({ current, report, onApply, disabled }: { current: Next; report: PolicyTestReport | null; onApply: (next: Next, override: boolean) => void; disabled?: boolean }) {
  const [pending, setPending] = useState<Next | null>(null);
  const [override, setOverride] = useState(false);
  const summary = confirmSummary(report);
  function request(next: Next) {
    if (next.mode === current.mode && next.fail === current.fail) return;
    if (needsConfirm(current, next)) {
      setOverride(false);
      setPending(next);
    } else onApply(next, false);
  }
  return (
    <div className="flex flex-wrap items-center gap-3" data-testid="mode-control">
      <ToggleGroup value={[current.mode]} onValueChange={(v) => v[0] && request({ ...current, mode: v[0] as Mode })} variant="outline" size="sm" aria-label="Mode" disabled={disabled}>
        <ToggleGroupItem value="shadow">Shadow</ToggleGroupItem>
        <ToggleGroupItem value="enforce">Enforce</ToggleGroupItem>
      </ToggleGroup>
      <div className="flex items-center gap-2 text-sm">
        <span className="text-muted-foreground">fail</span>
        <Select items={[{ value: "open", label: "open" }, { value: "closed", label: "closed" }]} value={current.fail} onValueChange={(v) => v && request({ ...current, fail: v as FailMode })} disabled={disabled}>
          <SelectTrigger size="sm" aria-label="Fail mode" className="w-24"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="open">open</SelectItem>
            <SelectItem value="closed">closed</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <AlertDialog open={pending != null} onOpenChange={(o) => !o && setPending(null)}>
        <AlertDialogContent data-testid="mode-confirm">
          <AlertDialogHeader>
            <AlertDialogTitle>{pending?.mode === "enforce" && current.mode === "shadow" ? "Start enforcing this policy?" : "Fail closed?"}</AlertDialogTitle>
            <AlertDialogDescription>
              {pending?.mode === "enforce" && current.mode === "shadow" ? "Blocked actions will really be blocked. " : "If the gateway cannot decide, the action will be refused. "}
              <span data-testid="confirm-numbers">{summary.text}</span>
            </AlertDialogDescription>
          </AlertDialogHeader>
          {pending?.mode === "enforce" && current.mode === "shadow" ? (
            <div className="flex items-center gap-2">
              <Switch id="override" checked={override} onCheckedChange={setOverride} />
              <Label htmlFor="override" className="text-xs">Override the test gate (recorded in the audit log)</Label>
            </div>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => pending && onApply(pending, override)}>{pending?.mode === "enforce" && current.mode === "shadow" ? "Enforce" : "Fail closed"}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
