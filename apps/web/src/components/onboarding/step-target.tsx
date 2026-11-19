"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";

import { LoaderCircle } from "@/components/animate-ui/icons/loader-circle";
import { RiskBadge } from "@/components/shared/badges";
import { useToast } from "@/components/shared/use-toast";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useWorld, useWorldList } from "@/lib/api/hooks/read";
import { useCreateAgentVersion } from "@/lib/api/hooks/write";

import { profileKey } from "./step-agent";
import { agentStepSchema, targetStepSchema, toVersionBody, type TargetStep } from "./wizard-schema";

type Kind = TargetStep["kind"];
const DEFAULT_MODEL = "openrouter/deepseek/deepseek-v4-flash";

function defaults(kind: Kind): TargetStep {
  switch (kind) {
    case "hosted":
      return { kind, model: DEFAULT_MODEL, system_prompt: "", temperature: 0, world_id: "", tools: null };
    case "openai_compat":
      return { kind, base_url: "", model: "", api_key_secret: "", wired: false, world_id: "" };
    case "http":
      return { kind, url: "", method: "POST", headers: "", body_template: '{"message": "{{user_message}}"}', reply_path: "", conversation_id_path: "", stateful: false, wired: false, world_id: "" };
  }
}

function Err({ msg }: { msg?: string }) {
  return msg ? <p role="alert" className="text-destructive text-xs">{msg}</p> : null;
}

function WorldPreview({ worldId, tools, onTools }: { worldId: string; tools: string[] | null; onTools: (t: string[] | null) => void }) {
  const w = useWorld(worldId || null);
  if (!worldId) return null;
  if (w.isLoading) return <Skeleton className="h-16 w-full" />;
  const all = w.data?.tools ?? [];
  return (
    <div className="flex flex-col gap-2 rounded-md border p-2">
      <div className="flex items-center justify-between">
        <span className="text-xs">{all.length} tools in this world</span>
        <label className="flex items-center gap-2 text-xs">
          <Switch checked={tools === null} onCheckedChange={(c) => onTools(c ? null : all.map((t) => t.name))} aria-label="Allow all tools" />
          Allow all tools
        </label>
      </div>
      <ul className="grid gap-1 sm:grid-cols-2">
        {all.map((t) => (
          <li key={t.name} className="flex items-center gap-2 text-xs">
            {tools !== null ? (
              <Checkbox
                checked={tools.includes(t.name)}
                onCheckedChange={(c) => onTools(c ? [...tools, t.name] : tools.filter((x) => x !== t.name))}
                aria-label={`Allow ${t.name}`}
              />
            ) : null}
            <span className="font-mono">{t.name}</span> <RiskBadge risk={t.risk} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function TargetForm({ kind, agentId, onDone }: { kind: Kind; agentId: string; onDone: (versionId: string) => void }) {
  const toast = useToast();
  const worlds = useWorldList();
  const create = useCreateAgentVersion(agentId);
  const form = useForm<TargetStep>({ resolver: zodResolver(targetStepSchema) as never, defaultValues: defaults(kind) });
  const { register, handleSubmit, control, watch, setValue, formState } = form;
  const errs = formState.errors as Record<string, { message?: string } | undefined>;
  const worldId = watch("world_id") as string;
  const tools = (watch("tools" as never) ?? null) as string[] | null;

  const submit = handleSubmit(async (values) => {
    const rawProfile = sessionStorage.getItem(profileKey(agentId));
    const profile = agentStepSchema.safeParse(rawProfile ? JSON.parse(rawProfile) : {});
    if (!profile.success) {
      toast.error(new Error("The agent profile from step 1 is missing. Go back and fill it in again."), "Missing profile");
      return;
    }
    try {
      const v = await create.mutateAsync(toVersionBody(profile.data, values));
      onDone(v.id);
    } catch (err) {
      toast.error(err, "Could not save the target");
    }
  });

  const worldField = (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="world">World</Label>
      {worlds.isLoading ? (
        <Skeleton className="h-8 w-full" />
      ) : (
        <Controller
          control={control}
          name="world_id"
          render={({ field }) => (
            <Select items={(worlds.data?.items ?? []).map((w) => ({ value: w.id, label: w.id }))} value={field.value || ""} onValueChange={(v) => field.onChange(v ?? "")}>
              <SelectTrigger id="world" aria-label="World" className="w-full"><SelectValue placeholder="Choose a world" /></SelectTrigger>
              <SelectContent>
                {(worlds.data?.items ?? []).map((w) => <SelectItem key={w.id} value={w.id}>{w.id}</SelectItem>)}
              </SelectContent>
            </Select>
          )}
        />
      )}
      <Err msg={errs.world_id?.message} />
    </div>
  );

  return (
    <form onSubmit={submit} className="flex max-w-2xl flex-col gap-4" noValidate>
      {kind === "hosted" ? (
        <>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="model">Model</Label>
            <Input id="model" className="font-mono" {...register("model" as never)} />
            <Err msg={errs.model?.message} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="system_prompt">System prompt</Label>
            <Textarea id="system_prompt" rows={10} className="font-mono text-xs" {...register("system_prompt" as never)} />
            <Err msg={errs.system_prompt?.message} />
          </div>
          <Controller
            control={control}
            name={"temperature" as never}
            render={({ field }) => (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="temperature">Temperature <span className="font-mono">{Number(field.value ?? 0).toFixed(1)}</span></Label>
                <Slider id="temperature" thumbAlignment="center" min={0} max={2} step={0.1} value={[Number(field.value ?? 0)]} onValueChange={(v) => field.onChange(Array.isArray(v) ? v[0] : v)} aria-label="Temperature" />
              </div>
            )}
          />
          {worldField}
          <WorldPreview worldId={worldId} tools={tools} onTools={(t) => setValue("tools" as never, t as never)} />
        </>
      ) : null}
      {kind === "openai_compat" ? (
        <>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="base_url">Base URL</Label>
            <Input id="base_url" className="font-mono" placeholder="https://host.example/v1" {...register("base_url" as never)} />
            <Err msg={errs.base_url?.message} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="model">Model</Label>
            <Input id="model" className="font-mono" {...register("model" as never)} />
            <Err msg={errs.model?.message} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="secret">API key secret name</Label>
            <Input id="secret" className="font-mono" {...register("api_key_secret" as never)} />
            <p className="text-muted-foreground text-xs">Type the name of the secret. Create the secret with the CLI first.</p>
          </div>
          <Controller control={control} name={"wired" as never} render={({ field }) => (
            <label className="flex items-center gap-2 text-sm"><Switch checked={Boolean(field.value)} onCheckedChange={field.onChange} aria-label="Wired" /> Wired: the agent calls Gauntlet&apos;s mock tools</label>
          )} />
        </>
      ) : null}
      {kind === "http" ? (
        <>
          <div className="grid gap-3 sm:grid-cols-[6rem_1fr]">
            <div className="flex flex-col gap-1.5"><Label htmlFor="method">Method</Label><Input id="method" className="font-mono" {...register("method" as never)} /></div>
            <div className="flex flex-col gap-1.5"><Label htmlFor="url">URL</Label><Input id="url" className="font-mono" placeholder="https://host.example/chat" {...register("url" as never)} /><Err msg={errs.url?.message} /></div>
          </div>
          <div className="flex flex-col gap-1.5"><Label htmlFor="headers">Headers</Label><Textarea id="headers" rows={2} className="font-mono text-xs" placeholder="X-Key: value" {...register("headers" as never)} /></div>
          <div className="flex flex-col gap-1.5"><Label htmlFor="body">Body template</Label><Textarea id="body" rows={4} className="font-mono text-xs" {...register("body_template" as never)} /><Err msg={errs.body_template?.message} /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5"><Label htmlFor="reply">Reply path</Label><Input id="reply" className="font-mono" {...register("reply_path" as never)} /><Err msg={errs.reply_path?.message} /></div>
            <div className="flex flex-col gap-1.5"><Label htmlFor="conv">Conversation id path</Label><Input id="conv" className="font-mono" {...register("conversation_id_path" as never)} /></div>
          </div>
          <Controller control={control} name={"stateful" as never} render={({ field }) => (
            <label className="flex items-center gap-2 text-sm"><Switch checked={Boolean(field.value)} onCheckedChange={field.onChange} aria-label="Stateful" /> Stateful: the agent keeps its own conversation</label>
          )} />
          <Controller control={control} name={"wired" as never} render={({ field }) => (
            <label className="flex items-center gap-2 text-sm"><Switch checked={Boolean(field.value)} onCheckedChange={field.onChange} aria-label="Wired" /> Wired: the agent calls Gauntlet&apos;s mock tools</label>
          )} />
        </>
      ) : null}
      <div className="flex justify-end">
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? <LoaderCircle size={14} animate loop /> : null}
          Continue
        </Button>
      </div>
    </form>
  );
}

export function StepTarget({ agentId, onBack, onDone }: { agentId: string; onBack: () => void; onDone: (versionId: string) => void }) {
  const [kind, setKind] = useState<Kind>("hosted");
  const key = useMemo(() => kind, [kind]);
  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-base font-medium">How should Gauntlet reach it?</h2>
      <ToggleGroup value={[kind]} onValueChange={(v) => v[0] && setKind(v[0] as Kind)} variant="outline" aria-label="Target kind">
        <ToggleGroupItem value="hosted">Hosted <span className="text-muted-foreground text-xs">recommended</span></ToggleGroupItem>
        <ToggleGroupItem value="openai_compat">OpenAI-compatible</ToggleGroupItem>
        <ToggleGroupItem value="http">HTTP</ToggleGroupItem>
      </ToggleGroup>
      <TargetForm key={key} kind={kind} agentId={agentId} onDone={onDone} />
      <div><Button variant="ghost" onClick={onBack}>Back</Button></div>
    </div>
  );
}
