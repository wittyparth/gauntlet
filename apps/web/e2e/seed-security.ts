import type { APIRequestContext } from "@playwright/test";

import world from "./fixtures/dva_sql_world.json";
import scenarios from "./fixtures/dva_sql_scenarios.json";

type Json = Record<string, unknown>;

export const SQL_AGENT = "DVA SQL agent";
export const REMOTE_AGENT = "Remote agent (unverified)";
export const BENIGN_SUITE = "dva_sql_benign";

async function exists(ctx: APIRequestContext, path: string) {
  return (await ctx.get(`/api/gauntlet${path}`)).ok();
}

async function must(res: Awaited<ReturnType<APIRequestContext["post"]>>, what: string): Promise<Json> {
  if (!res.ok()) throw new Error(`${what} failed: ${res.status()} ${await res.text()}`);
  return (await res.json()) as Json;
}

async function ensureAgentVersion(
  ctx: APIRequestContext,
  name: string,
  target: Json,
  projectId: string,
): Promise<string> {
  const agents = (await (await ctx.get("/api/gauntlet/v1/agents?limit=200")).json()).items as { id: string; name: string }[];
  let agent = agents.find((a) => a.name === name);
  if (!agent) {
    agent = (await must(await ctx.post("/api/gauntlet/v1/agents", { data: { project_id: projectId, name } }), "create agent")) as never;
  }
  const versions = (await (await ctx.get(`/api/gauntlet/v1/agents/${agent.id}/versions`)).json()).items as { id: string }[];
  if (versions[0]) return versions[0].id;
  const v = await must(
    await ctx.post(`/api/gauntlet/v1/agents/${agent.id}/versions`, {
      data: { label: "v1", target, profile: { purpose: "SQL analytics assistant" }, world_id: "dva_sql" },
    }),
    "create version",
  );
  return v.id as string;
}

/**
 * Seeds a campaign with findings through the API: the DVA SQL world and its agent (scripted brain,
 * compose profile `dva`, `DVA_BRAIN=scripted`), one benign suite, an unverified remote agent, and a
 * small `tool_injection` campaign that the scripted fake gateway runs without any model call.
 * Idempotent: the campaign only runs when no finding exists yet.
 */
export async function seedSecurity(ctx: APIRequestContext): Promise<void> {
  await must(await ctx.post("/api/gauntlet/v1/attacks/import"), "attack library import");
  if (!(await exists(ctx, "/v1/worlds/dva_sql"))) await must(await ctx.post("/api/gauntlet/v1/worlds", { data: world }), "world");
  for (const s of scenarios) {
    if (!(await exists(ctx, `/v1/scenarios/${s.id}`))) await must(await ctx.post("/api/gauntlet/v1/scenarios", { data: s }), "scenario");
  }
  if (!(await exists(ctx, `/v1/suites/${BENIGN_SUITE}`))) {
    await must(
      await ctx.post("/api/gauntlet/v1/suites", { data: { id: BENIGN_SUITE, name: "DVA SQL benign", scenarios: scenarios.map((s) => s.id) } }),
      "suite",
    );
  }
  const projects = (await (await ctx.get("/api/gauntlet/v1/projects")).json()).items as { id: string }[];
  const projectId = projects[0].id;
  const version = await ensureAgentVersion(
    ctx,
    SQL_AGENT,
    { kind: "openai_compat", base_url: "http://dva-sql:8101/v1", model: "dva", wired: true },
    projectId,
  );
  await ensureAgentVersion(
    ctx,
    REMOTE_AGENT,
    { kind: "openai_compat", base_url: "https://agent.unverified.example.test/v1", model: "remote", wired: false },
    projectId,
  );

  const have = (await (await ctx.get("/api/gauntlet/v1/findings?limit=1")).json()).items as unknown[];
  if (have.length > 0) return;
  const camp = await must(
    await ctx.post("/api/gauntlet/v1/campaigns", {
      data: {
        agent_version_id: version,
        world_id: "dva_sql",
        benign_scenario_ids: scenarios.map((s) => s.id),
        categories: ["tool_injection"],
        max_attacks: 6,
        budget_usd_micros: 5_000_000,
      },
      timeout: 60_000,
    }),
    "campaign",
  );
  const id = camp.campaign_id as string;
  const deadline = Date.now() + 120_000;
  for (;;) {
    const run = (await (await ctx.get(`/api/gauntlet/v1/runs/${id}`)).json()) as { status: string };
    if (["done", "failed", "cancelled"].includes(run.status)) break;
    if (Date.now() > deadline) throw new Error(`campaign ${id} did not finish in time`);
    await new Promise((r) => setTimeout(r, 1000));
  }
}
