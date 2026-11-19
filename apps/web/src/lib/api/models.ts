/**
 * Readers for API responses.
 *
 * The API's OpenAPI document declares every response body as an open object (only request bodies
 * are modelled), so `schema.d.ts` cannot type them. These zod readers validate the shapes the
 * screens consume, as documented by contracts sections 1, 2, 5 and 9 and observed on the running
 * API. Request bodies and paths stay typed from the generated schema. Replace these with the
 * generated types as soon as the API declares response models (reported as a contract gap).
 */
import { z } from "zod";

const obj = z.looseObject;
const nullish = <T extends z.ZodType>(t: T) => t.nullish().transform((v) => v ?? null);

export const listOf = <T extends z.ZodType>(item: T) =>
  obj({ items: z.array(item), next_cursor: nullish(z.string()) });

export const projectSchema = obj({ id: z.string(), name: z.string() });
export type Project = z.infer<typeof projectSchema>;

export const agentSchema = obj({
  id: z.string(),
  project_id: z.string(),
  name: z.string(),
  latest_version_id: nullish(z.string()),
  created_at: z.string(),
});
export type Agent = z.infer<typeof agentSchema>;

export const profileSchema = obj({
  purpose: z.string(),
  audience: z.string().default(""),
  policies_text: z.string().default(""),
  forbidden_behaviors: z.array(z.string()).default([]),
  languages: z.array(z.string()).default([]),
});

export const targetSchema = obj({
  kind: z.string(),
  model: z.string().optional(),
  system_prompt: z.string().optional(),
  temperature: z.number().optional(),
  tools: nullish(z.array(z.string())),
  base_url: z.string().optional(),
  api_key_secret: nullish(z.string()),
  url: z.string().optional(),
  method: z.string().optional(),
  reply_path: z.string().optional(),
  stateful: z.boolean().optional(),
  wired: z.boolean().optional(),
});
export type Target = z.infer<typeof targetSchema>;

export const agentVersionSchema = obj({
  id: z.string(),
  agent_id: z.string(),
  label: z.string(),
  target: targetSchema,
  profile: profileSchema,
  world_id: nullish(z.string()),
  created_at: z.string(),
});
export type AgentVersion = z.infer<typeof agentVersionSchema>;

export const scenarioDocSchema = obj({
  id: z.string(),
  title: z.string(),
  goal: z.string(),
  version: z.number(),
  persona: z.string(),
  world: z.union([z.string(), z.record(z.string(), z.unknown())]),
  max_turns: z.number(),
  tags: z.record(z.string(), z.string()).default({}),
  hidden_facts: z.array(z.string()).default([]),
  rubrics: z.array(z.string()).default([]),
  success: z.unknown(),
  forbidden: z
    .array(
      obj({
        id: z.string(),
        description: z.string().default(""),
        severity: z.string(),
        check: z.unknown(),
      }),
    )
    .default([]),
  persona_overrides: z.record(z.string(), z.unknown()).default({}),
  world_overrides: z.record(z.string(), z.unknown()).default({}),
  opening_message: nullish(z.string()),
  attack: z.unknown().optional(),
});
export type ScenarioDoc = z.infer<typeof scenarioDocSchema>;

export const scenarioRecordSchema = obj({
  id: z.string(),
  status: z.string(),
  source: z.string(),
  version: z.number(),
  created_at: z.string(),
  scenario: scenarioDocSchema,
});
export type ScenarioRecord = z.infer<typeof scenarioRecordSchema>;

export const suiteSchema = obj({
  id: z.string(),
  name: z.string(),
  scenarios: z.array(z.string()),
  repetitions: z.number(),
});
export type Suite = z.infer<typeof suiteSchema>;

export const toolSpecSchema = obj({
  name: z.string(),
  description: z.string().default(""),
  risk: z.string(),
  handler: obj({ kind: z.string() }),
  honeytool: z.boolean().default(false),
  untrusted_output: z.boolean().default(false),
});
export type ToolSpec = z.infer<typeof toolSpecSchema>;

export const worldSchema = obj({
  id: z.string(),
  tools: z.array(toolSpecSchema),
  clock_start: z.string().optional(),
});
export type World = z.infer<typeof worldSchema>;

export const countsSchema = obj({
  total: z.number(),
  queued: z.number().default(0),
  leased: z.number().default(0),
  done: z.number().default(0),
  cancelled: z.number().default(0),
  by_outcome: z.record(z.string(), z.number()).default({}),
});
export type Counts = z.infer<typeof countsSchema>;

export const runSchema = obj({
  id: z.string(),
  suite_id: z.string(),
  agent_version_id: z.string(),
  status: z.string(),
  repetitions: z.number(),
  budget_usd_micros: z.number(),
  spent_usd_micros: z.number(),
  reserved_usd_micros: z.number().default(0),
  counts: countsSchema,
  created_at: z.string(),
  finished_at: nullish(z.string()),
  manifest: obj({
    agent_version: obj({ id: z.string(), label: z.string(), agent_id: z.string() }).optional(),
  }).optional(),
});
export type Run = z.infer<typeof runSchema>;

export const episodeRowSchema = obj({
  id: z.string(),
  run_id: z.string(),
  scenario_id: z.string(),
  rep: z.number(),
  status: z.string(),
  outcome: nullish(z.string()),
  termination: nullish(z.string()),
  cost_usd_micros: z.number().default(0),
  world_fidelity: nullish(z.string()),
  created_at: z.string(),
  finished_at: nullish(z.string()),
});
export type EpisodeRow = z.infer<typeof episodeRowSchema>;

export const eventSchema = obj({
  kind: z.string(),
  actor: z.string(),
  seq: z.number(),
  sim_time: z.string(),
  wall_ms: z.number().default(0),
  payload: z.record(z.string(), z.unknown()).default({}),
  origin: nullish(
    obj({ trust: z.string(), source: nullish(z.string()), markers: z.array(z.string()).default([]) }),
  ),
  cost: nullish(
    obj({
      model: nullish(z.string()),
      usd_micros: z.number().default(0),
      input_tokens: z.number().default(0),
      output_tokens: z.number().default(0),
    }),
  ),
});
export type EpisodeEvent = z.infer<typeof eventSchema>;

export const evidenceSchema = obj({
  seq: z.number(),
  quote: nullish(z.string()),
  note: nullish(z.string()),
});
export type Evidence = z.infer<typeof evidenceSchema>;

export const verdictSchema = obj({
  criterion: z.string(),
  evaluator: z.string(),
  result: z.string(),
  severity: z.string(),
  hard_fail: z.boolean().default(false),
  stage: z.string(),
  model: nullish(z.string()),
  confidence: nullish(z.number()),
  reasoning: z.string().default(""),
  evidence: z.array(evidenceSchema).default([]),
  cost: nullish(obj({ usd_micros: z.number().default(0) })),
});
export type Verdict = z.infer<typeof verdictSchema>;

export const diffChangeSchema = obj({
  collection: z.string(),
  id: z.string(),
  kind: z.enum(["added", "removed", "changed"]),
  fields: z.array(obj({ path: z.string(), old: z.unknown(), new: z.unknown() })).default([]),
  record: z.unknown().optional(),
  seqs: z.array(z.number()).default([]),
});
export type DiffChange = z.infer<typeof diffChangeSchema>;

export const episodeDetailSchema = episodeRowSchema.extend({
  attempt: z.number().default(0),
  partial: z.boolean().default(false),
  scenario: obj({
    id: z.string(),
    title: z.string(),
    goal: z.string(),
    max_turns: z.number(),
  }),
  events: z.array(eventSchema),
  verdicts: z.array(verdictSchema).default([]),
  diff: nullish(obj({ changes: z.array(diffChangeSchema) })),
  tools: z.record(z.string(), z.string()).default({}),
});
export type EpisodeDetail = z.infer<typeof episodeDetailSchema>;

export const reportSchema = obj({
  run_id: z.string(),
  counted: z.number(),
  excluded: z.record(z.string(), z.number()).default({}),
  pass_rate: nullish(z.number()),
  ci_low: nullish(z.number()),
  ci_high: nullish(z.number()),
  per_scenario: z.array(
    obj({
      scenario_id: z.string(),
      title: z.string(),
      counted: z.number(),
      passed: z.number(),
      rate: nullish(z.number()),
      ci_low: nullish(z.number()),
      ci_high: nullish(z.number()),
      episode_ids: z.array(z.string()).default([]),
    }),
  ),
  dimensions: z
    .array(
      obj({
        criterion: z.string(),
        severity: z.string(),
        passed: z.number(),
        failed: z.number(),
        na: z.number(),
        error: z.number(),
      }),
    )
    .default([]),
  cost_usd_micros: z.number().default(0),
  failures: z
    .array(
      obj({ episode_id: z.string(), scenario_id: z.string(), reasons: z.array(z.string()).default([]) }),
    )
    .default([]),
  caution: nullish(
    obj({
      self_preference: z.boolean().default(false),
      world_fidelity: nullish(z.string()),
      uncalibrated_rubrics: z.array(z.string()).default([]),
      reduced_coverage: z.boolean().default(false),
    }),
  ),
});
export type Report = z.infer<typeof reportSchema>;

export const estimateSchema = obj({
  valid: z.boolean(),
  errors: z.array(z.unknown()).default([]),
  warnings: z.array(z.unknown()).default([]),
  episode_count: z.number().default(0),
  estimate_usd_micros: obj({ low: z.number(), expected: z.number(), high: z.number() }),
});
export type Estimate = z.infer<typeof estimateSchema>;

export const createdRunSchema = obj({ id: z.string() });

/** Terminal run statuses (contract: runs.status). */
export const TERMINAL_RUN_STATUSES = ["done", "cancelled", "failed"] as const;
export const isTerminalRun = (status: string) =>
  (TERMINAL_RUN_STATUSES as readonly string[]).includes(status);
