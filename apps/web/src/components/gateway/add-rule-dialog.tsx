"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { PolicyRule } from "@/lib/api/hooks/policies";

const SLUG = /^[a-z0-9][a-z0-9_-]*$/;

/** A starter rule: id, a description and the tool it watches. The form then edits the rest. */
export function AddRuleDialog({ onAdd, taken }: { onAdd: (rule: PolicyRule) => Promise<unknown>; taken: string[] }) {
  const [open, setOpen] = useState(false);
  const [id, setId] = useState("");
  const [description, setDescription] = useState("");
  const [tool, setTool] = useState("");
  const [busy, setBusy] = useState(false);
  const error = id && !SLUG.test(id) ? "Use lowercase letters, digits, - and _." : taken.includes(id) ? "This rule id is taken." : null;
  const ready = Boolean(id && description.trim() && tool.trim() && !error);

  async function submit() {
    setBusy(true);
    try {
      await onAdd({ id, description: description.trim(), severity: "medium", action: "log", strict: false, when: { type: "tool_called", tool: tool.trim() } as never });
      setOpen(false);
      setId("");
      setDescription("");
      setTool("");
    } catch {
      // the caller reports the error; keep the dialog open
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" variant="outline" />}>Add rule</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a rule</DialogTitle>
          <DialogDescription>Starts as a log rule on one tool. Change the check, severity and action afterwards.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="new-rule-id">Rule id</Label>
            <Input id="new-rule-id" value={id} onChange={(e) => setId(e.target.value)} aria-invalid={Boolean(error)} />
            {error ? <p className="text-destructive text-xs">{error}</p> : null}
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="new-rule-desc">Description</Label>
            <Input id="new-rule-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="new-rule-tool">Tool to watch</Label>
            <Input id="new-rule-tool" value={tool} onChange={(e) => setTool(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button disabled={!ready || busy} onClick={() => void submit()}>Add rule</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
