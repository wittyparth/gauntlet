import { z } from "zod";

import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];

const lines = (s: string) =>
  s
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

export const agentStepSchema = z.object({
  name: z.string().trim().min(1, "Name the agent."),
  purpose: z.string().trim().min(1, "Say what the agent is for."),
  audience: z.string().default(""),
  policies_text: z.string().default(""),
  forbidden_behaviors: z.string().default(""),
  languages: z.string().default("en"),
});
export type AgentStep = z.infer<typeof agentStepSchema>;

const jsonObject = z.string().refine((s) => {
  try {
    const v: unknown = JSON.parse(s);
    return typeof v === "object" && v !== null && !Array.isArray(v);
  } catch {
    return false;
  }
}, "Enter a JSON object.");

const hosted = z.object({
  kind: z.literal("hosted"),
  model: z.string().trim().min(1, "Choose a model."),
  system_prompt: z.string().trim().min(1, "Add a system prompt."),
  temperature: z.number().min(0).max(2),
  world_id: z.string().min(1, "Choose a world."),
  tools: z.array(z.string()).nullable(),
});
const openaiCompat = z.object({
  kind: z.literal("openai_compat"),
  base_url: z.string().url("Enter a full URL, like https://host/v1."),
  model: z.string().trim().min(1, "Enter the model name."),
  api_key_secret: z.string().default(""),
  wired: z.boolean().default(false),
  world_id: z.string().default(""),
});
const http = z.object({
  kind: z.literal("http"),
  url: z.string().url("Enter a full URL."),
  method: z.string().trim().min(1).default("POST"),
  headers: z.string().default(""),
  body_template: jsonObject,
  reply_path: z.string().trim().min(1, "Say where the reply is in the response."),
  conversation_id_path: z.string().default(""),
  stateful: z.boolean().default(false),
  wired: z.boolean().default(false),
  world_id: z.string().default(""),
});

export const targetStepSchema = z.discriminatedUnion("kind", [hosted, openaiCompat, http]);
export type TargetStep = z.infer<typeof targetStepSchema>;

export { runStepSchema, budgetMicros, type RunStep } from "@/components/shared/run-config";

export function toProfile(a: AgentStep): Schemas["AgentProfile"] {
  return {
    purpose: a.purpose,
    audience: a.audience,
    policies_text: a.policies_text,
    forbidden_behaviors: lines(a.forbidden_behaviors),
    languages: a.languages
      .split(",")
      .map((l) => l.trim())
      .filter(Boolean),
  };
}

function toHeaders(s: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const l of lines(s)) {
    const i = l.indexOf(":");
    if (i > 0) out[l.slice(0, i).trim()] = l.slice(i + 1).trim();
  }
  return out;
}

export function toVersionBody(agent: AgentStep, target: TargetStep, label = "v1"): Schemas["VersionIn"] {
  const profile = toProfile(agent);
  const world_id = target.world_id || null;
  switch (target.kind) {
    case "hosted":
      return {
        label,
        profile,
        world_id,
        target: {
          kind: "hosted",
          model: target.model,
          system_prompt: target.system_prompt,
          temperature: target.temperature,
          tools: target.tools,
        },
      };
    case "openai_compat":
      return {
        label,
        profile,
        world_id,
        target: {
          kind: "openai_compat",
          base_url: target.base_url,
          model: target.model,
          api_key_secret: target.api_key_secret || null,
          wired: target.wired,
        },
      };
    case "http":
      return {
        label,
        profile,
        world_id,
        target: {
          kind: "http",
          url: target.url,
          method: target.method,
          headers: toHeaders(target.headers),
          body_template: JSON.parse(target.body_template) as Record<string, unknown>,
          reply_path: target.reply_path,
          conversation_id_path: target.conversation_id_path || null,
          stateful: target.stateful,
          wired: target.wired,
        },
      };
  }
}
