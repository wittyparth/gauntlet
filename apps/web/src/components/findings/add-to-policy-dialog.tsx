"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useToast } from "@/components/shared/use-toast";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAddRuleTo, usePolicyList, type PolicyRule } from "@/lib/api/hooks/policies";

/** Adds a finding's suggested rule to a policy's draft, then opens the editor on it. */
export function AddToPolicyDialog({ rule }: { rule: PolicyRule }) {
  const router = useRouter();
  const toast = useToast();
  const policies = usePolicyList();
  const add = useAddRuleTo();
  const [open, setOpen] = useState(false);
  const [policyId, setPolicyId] = useState<string | null>(null);
  const list = policies.data ?? [];
  const chosen = policyId ?? list[0]?.id ?? null;

  async function submit() {
    if (!chosen) return;
    try {
      await add.mutateAsync({ policyId: chosen, rule });
      toast.success("Rule added to the draft", "Review it in the editor, run the offline test, then publish.");
      setOpen(false);
      router.push(`/gateway/policies/${chosen}`);
    } catch (e) {
      toast.error(e, "Could not add the rule");
    }
  }
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" variant="outline" />}>Add to policy</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add this rule to a policy</DialogTitle>
          <DialogDescription>The rule joins the policy&apos;s next draft version. Nothing is enforced until you publish it.</DialogDescription>
        </DialogHeader>
        {list.length === 0 ? (
          <p className="text-muted-foreground text-sm" data-testid="no-policies">
            No policy yet. <Link className="underline" href="/gateway/policies">Create one first.</Link>
          </p>
        ) : (
          <Select items={list.map((p) => ({ value: p.id, label: p.name }))} value={chosen} onValueChange={(v) => v && setPolicyId(v)}>
            <SelectTrigger aria-label="Policy" className="w-full"><SelectValue placeholder="Choose a policy" /></SelectTrigger>
            <SelectContent>{list.map((p) => <SelectItem key={p.id} value={p.id}>{p.name} (v{p.version}, {p.status})</SelectItem>)}</SelectContent>
          </Select>
        )}
        <DialogFooter>
          <Button disabled={!chosen || add.isPending} onClick={() => void submit()}>Add rule</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
