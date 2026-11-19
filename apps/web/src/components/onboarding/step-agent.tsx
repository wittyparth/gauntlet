"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import { LoaderCircle } from "@/components/animate-ui/icons/loader-circle";
import { useToast } from "@/components/shared/use-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useCurrentProject } from "@/lib/api/hooks/read";
import { useCreateAgent, useCreateProject } from "@/lib/api/hooks/write";

import { agentStepSchema, type AgentStep } from "./wizard-schema";

export const profileKey = (agentId: string) => `gauntlet:wizard:${agentId}`;

function Field({ id, label, error, children, hint }: { id: string; label: string; error?: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && !error ? <p className="text-muted-foreground text-xs">{hint}</p> : null}
      {error ? <p role="alert" className="text-destructive text-xs">{error}</p> : null}
    </div>
  );
}

export function StepAgent({ onDone }: { onDone: (agentId: string) => void }) {
  const toast = useToast();
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => setHydrated(true), []);
  const { project, isLoading } = useCurrentProject();
  const createProject = useCreateProject();
  const createAgent = useCreateAgent();
  const form = useForm<AgentStep>({
    resolver: zodResolver(agentStepSchema) as never,
    defaultValues: { name: "", purpose: "", audience: "", policies_text: "", forbidden_behaviors: "", languages: "en" },
  });
  const { register, handleSubmit, formState } = form;
  const e = formState.errors;

  const submit = handleSubmit(async (values) => {
    try {
      const proj = project ?? (await createProject.mutateAsync({ name: "Default" }));
      const agent = await createAgent.mutateAsync({ project_id: proj.id, name: values.name });
      sessionStorage.setItem(profileKey(agent.id), JSON.stringify(values));
      onDone(agent.id);
    } catch (err) {
      toast.error(err, "Could not create the agent");
    }
  });
  const pending = createAgent.isPending || createProject.isPending;

  return (
    <form onSubmit={submit} className="flex max-w-2xl flex-col gap-4" noValidate>
      <h2 className="text-base font-medium">What is the agent?</h2>
      <Field id="name" label="Name" error={e.name?.message}>
        <Input id="name" aria-invalid={Boolean(e.name)} {...register("name")} />
      </Field>
      <Field id="purpose" label="Purpose" error={e.purpose?.message} hint="One sentence: what is this agent for?">
        <Input id="purpose" aria-invalid={Boolean(e.purpose)} {...register("purpose")} />
      </Field>
      <Field id="audience" label="Audience">
        <Input id="audience" {...register("audience")} />
      </Field>
      <Field id="policies" label="Policies" hint="The rules the agent must follow, in plain text.">
        <Textarea id="policies" rows={5} {...register("policies_text")} />
      </Field>
      <Field id="forbidden" label="Forbidden behaviors" hint="One per line.">
        <Textarea id="forbidden" rows={3} {...register("forbidden_behaviors")} />
      </Field>
      <Field id="languages" label="Languages" hint="Comma separated, like en, es.">
        <Input id="languages" {...register("languages")} />
      </Field>
      <div className="flex justify-end">
        <Button type="submit" disabled={!hydrated || pending || isLoading}>
          {pending ? <LoaderCircle size={14} animate loop /> : null}
          Continue
        </Button>
      </div>
    </form>
  );
}
