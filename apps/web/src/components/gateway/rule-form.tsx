"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { toApiError } from "@/lib/api/errors";
import type { PolicyRule } from "@/lib/api/hooks/policies";

import { CheckEditor } from "./check-editor";
import { parseCheck } from "./check-validation";

const SEVERITIES = ["low", "medium", "high", "critical"] as const;
const ACTIONS = ["block", "require_approval", "redact", "log"] as const;

const schema = z.object({
  description: z.string().trim().min(1, "Describe the rule."),
  severity: z.enum(SEVERITIES),
  action: z.enum(ACTIONS),
  message: z.string(),
  when: z.string().refine((v) => parseCheck(v).ok, "The check is not valid."),
});
type Values = z.infer<typeof schema>;

/** One rule. Saving a rule edits the draft; publishing makes the next version. */
export function RuleForm({ rule, onSave, saving }: { rule: PolicyRule; onSave: (rule: PolicyRule) => Promise<unknown>; saving: boolean }) {
  const [serverError, setServerError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    mode: "onChange",
    defaultValues: {
      description: rule.description,
      severity: rule.severity,
      action: rule.action,
      message: rule.message ?? "",
      when: JSON.stringify(rule.when, null, 2),
    },
  });
  const { isDirty, isValid } = form.formState;
  async function submit(v: Values) {
    const parsed = parseCheck(v.when);
    if (!parsed.ok) return;
    setServerError(null);
    try {
      await onSave({ ...rule, description: v.description, severity: v.severity, action: v.action, message: v.message || null, when: parsed.value as never });
      form.reset(v);
    } catch (e) {
      setServerError(toApiError(e).message);
    }
  }
  return (
    <form onSubmit={form.handleSubmit(submit)} className="flex flex-col gap-3" data-testid="rule-form" aria-label={`Rule ${rule.id}`}>
      <div className="flex items-center gap-2">
        <h3 className="font-mono text-sm">{rule.id}</h3>
        {isDirty ? <Badge variant="outline" data-testid="unsaved">Unsaved</Badge> : null}
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="rule-description">Description</Label>
        <Input id="rule-description" {...form.register("description")} aria-invalid={Boolean(form.formState.errors.description)} />
        {form.formState.errors.description ? <p className="text-destructive text-xs">{form.formState.errors.description.message}</p> : null}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <Label>Severity</Label>
          <Controller
            control={form.control}
            name="severity"
            render={({ field }) => (
              <Select items={SEVERITIES.map((s) => ({ value: s, label: s }))} value={field.value} onValueChange={(v) => v && field.onChange(v)}>
                <SelectTrigger aria-label="Severity" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>{SEVERITIES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            )}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label>Action</Label>
          <Controller
            control={form.control}
            name="action"
            render={({ field }) => (
              <Select items={ACTIONS.map((s) => ({ value: s, label: s.replace("_", " ") }))} value={field.value} onValueChange={(v) => v && field.onChange(v)}>
                <SelectTrigger aria-label="Action" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>{ACTIONS.map((s) => <SelectItem key={s} value={s}>{s.replace("_", " ")}</SelectItem>)}</SelectContent>
              </Select>
            )}
          />
        </div>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="rule-message">Message shown when it fires</Label>
        <Textarea id="rule-message" rows={2} {...form.register("message")} />
      </div>
      <div className="flex flex-col gap-1">
        <Label>When (JSON)</Label>
        <Controller control={form.control} name="when" render={({ field }) => <CheckEditor value={field.value} onChange={field.onChange} serverError={serverError} />} />
      </div>
      <div className="flex items-center gap-2">
        <Button type="submit" disabled={!isDirty || !isValid || saving}>Save rule</Button>
        <Button type="button" variant="ghost" disabled={!isDirty} onClick={() => { form.reset(); setServerError(null); }}>Discard</Button>
      </div>
    </form>
  );
}
