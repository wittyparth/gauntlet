import { test as base, expect, type APIRequestContext, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";

type Json = Record<string, unknown>;

async function get(request: APIRequest, path: string): Promise<Json> {
  const res = await request.get(`/api/gauntlet${path}`);
  if (!res.ok()) throw new Error(`seed lookup ${path} -> ${res.status()}`);
  return (await res.json()) as Json;
}
type APIRequest = APIRequestContext;

/** Finds seeded records through the proxy: no hard-coded ids. */
export function seededHelpers(request: APIRequest) {
  const items = async (path: string) => ((await get(request, path)).items as Json[]) ?? [];
  return {
    async run(): Promise<{ id: string; suite_id: string }> {
      const runs = await items("/v1/runs?limit=200");
      // The seeded demo run (ecommerce smoke suite) first; other specs create runs of their own.
      const run = runs.find((r) => r.id === "run_demo") ?? runs.find((r) => r.status === "done") ?? runs[0];
      return run as { id: string; suite_id: string };
    },
    async failedEpisode(): Promise<{ id: string; run_id: string; scenario_id: string }> {
      // The first failed episode that shows everything: a verdict with evidence and a state change.
      const runs = await items("/v1/runs?limit=200");
      let fallback: { id: string; run_id: string; scenario_id: string } | null = null;
      for (const r of runs.filter((r) => r.status === "done")) {
        const eps = await items(`/v1/runs/${r.id as string}/episodes?limit=200&outcome=failed`);
        for (const e of eps.filter((e) => e.outcome === "failed")) {
          const ep = e as { id: string; run_id: string; scenario_id: string };
          fallback ??= ep;
          const detail = await get(request, `/v1/episodes/${ep.id}`);
          const verdicts = (detail.verdicts as { evidence: unknown[] }[]) ?? [];
          const changes = ((detail.diff as { changes: unknown[] } | null)?.changes ?? []).length;
          if (verdicts.some((v) => v.evidence.length > 0) && changes > 0) return ep;
        }
      }
      if (fallback) return fallback;
      throw new Error("no seeded failed episode");
    },
    async scenario(): Promise<{ id: string; scenario: { id: string; title: string; goal: string } }> {
      return (await items("/v1/scenarios?limit=200"))[0] as never;
    },
    /** The first finding of the seeded DVA SQL campaign. */
    async finding(): Promise<{ id: string; title: string; agent_version_id: string }> {
      // Prefer the seeded DVA SQL agent's findings (they carry reproducers and evidence).
      const sql = await this.sqlAgentVersion().catch(() => null);
      const scoped = sql ? await items(`/v1/findings?limit=200&agent_version_id=${sql.agent_version_id}`) : [];
      const found = scoped.length > 0 ? scoped : await items("/v1/findings?limit=200");
      if (found.length === 0) {
        throw new Error("no findings: start compose with the dva profile (DVA_BRAIN=scripted) and re-run e2e");
      }
      return found[0] as never;
    },
    /**
     * The seeded DVA SQL agent's first version. The launch specs need this agent but no findings,
     * so they do not depend on the compose `dva` profile having produced a campaign.
     */
    async sqlAgentVersion(): Promise<{ agent_version_id: string }> {
      const agents = (await items("/v1/agents?limit=200")) as { id: string; name: string }[];
      const agent = agents.find((a) => a.name === "DVA SQL agent");
      if (!agent) throw new Error("no DVA SQL agent: the e2e global setup seeds it (seed-security.ts)");
      const versions = await items(`/v1/agents/${agent.id}/versions`);
      return { agent_version_id: (versions[0] as { id: string }).id };
    },
    async agent(): Promise<{ id: string; name: string }> {
      const agents = (await items("/v1/agents?limit=200")) as { id: string; name: string }[];
      // The seed's agent has runs; the onboarding spec creates extra agents without any.
      return (agents.find((a) => /demo/i.test(a.name)) ?? agents[agents.length - 1]) as never;
    },
  };
}

export const test = base.extend<{
  consoleErrors: string[];
  seeded: ReturnType<typeof seededHelpers>;
  shot: (page: Page, name: string) => Promise<void>;
}>({
  consoleErrors: [
    async ({ page }, use) => {
      const errors: string[] = [];
      page.on("console", (m) => {
        if (m.type() === "error") errors.push(`console.error: ${m.text()}`);
      });
      page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
      await use(errors);
      expect(errors, "no console errors").toEqual([]);
    },
    { auto: true },
  ],
  seeded: async ({ request }, use) => use(seededHelpers(request)),
  shot: async ({}, use) => {
    mkdirSync("e2e/.screens", { recursive: true });
    await use(async (page, name) => {
      await page.screenshot({ path: `e2e/.screens/${name}.png`, fullPage: true });
    });
  },
});

export { expect };

/** Fulfil a route with the contract error envelope. */
export function errorEnvelope(status: number, code = "internal", message = "internal error") {
  return { status, contentType: "application/json", body: JSON.stringify({ error: { code, message, detail: null } }) };
}
