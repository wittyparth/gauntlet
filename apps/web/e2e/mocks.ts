import type { Page } from "@playwright/test";

export const RUN_ID = "run_live";
export const EP_ID = "ep_live_1";

type Snapshot = { done: number; spent: number; events: number };

export const run = (s: Snapshot, status = "running") => ({
  id: RUN_ID,
  suite_id: "smoke",
  agent_version_id: "agv_demo",
  status,
  repetitions: 1,
  seed: 1,
  budget_usd_micros: 2_000_000,
  reserved_usd_micros: 0,
  spent_usd_micros: s.spent,
  baseline_of: null,
  counts: { total: 30, queued: 30 - s.done - 1, leased: 1, done: s.done, cancelled: 0, by_outcome: { passed: s.done - 2, failed: 2 } },
  manifest: { agent_version: { id: "agv_demo", label: "v1", agent_id: "agt_demo" } },
  created_at: new Date(Date.now() - 120_000).toISOString(),
  finished_at: null,
});

export const episodes = (s: Snapshot) => ({
  items: [
    { id: EP_ID, run_id: RUN_ID, scenario_id: "scn_live_a", rep: 0, status: "leased", outcome: null, termination: null, cost_usd_micros: 1200, world_fidelity: "full", created_at: new Date().toISOString(), finished_at: null },
    { id: "ep_live_0", run_id: RUN_ID, scenario_id: "scn_live_b", rep: 0, status: "done", outcome: "passed", termination: "user_done", cost_usd_micros: 900, world_fidelity: "full", created_at: new Date().toISOString(), finished_at: new Date().toISOString() },
  ].slice(0, s.done > 10 ? 2 : 2),
  next_cursor: null,
});

const ev = (seq: number, kind: string, actor: string, payload: Record<string, unknown>) => ({
  kind, actor, seq, sim_time: "2026-03-15T10:00:00Z", wall_ms: 0, payload, origin: null, cost: null,
});

export const episode = (s: Snapshot) => ({
  ...episodes(s).items[0],
  attempt: 0,
  partial: true,
  scenario: { id: "scn_live_a", title: "Refund outside window", goal: "Get a refund", max_turns: 8 },
  events: [
    ev(0, "episode_started", "platform", { scenario: "scn_live_a" }),
    ev(1, "user_message", "user", { text: "I want a refund for my order" }),
    ev(2, "agent_message", "agent", { text: "Let me look that up." }),
    ...(s.events > 3 ? [ev(3, "user_message", "user", { text: "It was delivered last month" })] : []),
  ],
  verdicts: [],
  diff: null,
  tools: {},
});

/** Serve scripted REST snapshots and a scripted SSE stream. `advance` flips A to B on the first stream request. */
export async function mockLiveRun(page: Page) {
  const state = { b: false };
  const snap = (): Snapshot => (state.b ? { done: 11, spent: 330_000, events: 4 } : { done: 10, spent: 310_000, events: 3 });
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  await page.route(`**/api/gauntlet/v1/runs/${RUN_ID}`, (r) => (r.request().method() === "GET" ? r.fulfill(json(run(snap()))) : r.fallback()));
  await page.route(`**/api/gauntlet/v1/runs/${RUN_ID}/episodes*`, (r) => r.fulfill(json(episodes(snap()))));
  await page.route(`**/api/gauntlet/v1/episodes/${EP_ID}*`, (r) => r.fulfill(json(episode(snap()))));
  await page.route(`**/api/gauntlet/v1/runs/${RUN_ID}/stream`, (r) => {
    const first = !state.b;
    state.b = true;
    return r.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream", "cache-control": "no-cache" },
      body: first
        ? 'event: run_update\ndata: {"run_id":"run_live"}\n\nevent: episode_update\ndata: {}\n\nevent: event\ndata: {}\n\n'
        : "event: run_update\ndata: {}\n\n",
    });
  });
  return state;
}
