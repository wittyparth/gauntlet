import { mkdirSync } from "node:fs";
import path from "node:path";

import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";

type Run = { id: string; suite_id: string; status: string; agent_version_id: string };

async function runPair(request: import("@playwright/test").APIRequestContext) {
  const res = await request.get("/api/gauntlet/v1/runs?limit=200");
  const runs = ((await res.json()) as { items: Run[] }).items.filter((r) => r.status === "done");
  const base = runs.find((r) => r.id === "run_demo") ?? runs[0];
  if (!base) return null;
  const other = runs.find((r) => r.id !== base.id && r.suite_id === base.suite_id);
  if (other) return { cand: other, base };
  // Only one finished run: start a second one of the same suite (the compose stack runs scripted models).
  const made = await request.post("/api/gauntlet/v1/runs", {
    data: { suite_id: base.suite_id, agent_version_id: base.agent_version_id, budget_usd_micros: 2_000_000, seed: 7, adaptive: false, include_drafts: false },
  });
  if (!made.ok()) return null;
  const id = ((await made.json()) as { id: string }).id;
  for (let i = 0; i < 90; i++) {
    const r = (await (await request.get(`/api/gauntlet/v1/runs/${id}`)).json()) as Run;
    if (r.status === "done") return { cand: r, base };
    await new Promise((res) => setTimeout(res, 2000));
  }
  return null;
}

const SHOTS = path.resolve(__dirname, "../../../.demo/shots");
async function themed(page: Page, name: string) {
  mkdirSync(SHOTS, { recursive: true });
  for (const scheme of ["dark", "light"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.evaluate((s) => localStorage.setItem("theme", s), scheme);
    await page.reload();
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: path.join(SHOTS, `${name}-${scheme}.png`), fullPage: true });
  }
}

test("compare: loads a comparison of two finished runs", async ({ page, request }) => {
  test.setTimeout(240_000);
  const pair = await runPair(request);
  test.skip(!pair, "needs two finished runs of one suite");
  await page.goto(`/runs/${pair!.cand.id}/compare?baseline=${pair!.base.id}`);
  await expect(page.getByTestId("verdict-banner")).toBeVisible();
  await expect(page.getByTestId("flip-table")).toBeVisible();
  await themed(page, "compare");
});

test("compare: asks for a baseline when none is chosen", async ({ page, seeded }) => {
  const run = await seeded.run();
  await page.goto(`/runs/${run.id}/compare`);
  await expect(page.getByText("Choose a baseline run")).toBeVisible();
});

test("review: renders the queue or its empty state", async ({ page }) => {
  await page.goto("/review");
  await expect(page.getByRole("heading", { level: 1, name: "Review" })).toBeVisible();
  await expect(page.getByTestId("empty-state").or(page.getByTestId("review-item"))).toBeVisible();
});

test("rubrics: lists rubrics and opens one", async ({ page }) => {
  await page.goto("/rubrics");
  await expect(page.getByRole("heading", { level: 1, name: "Rubrics" })).toBeVisible();
  await expect(page.getByTestId("rubric-row").first()).toBeVisible();
  await page.getByTestId("rubric-row").first().click();
  await expect(page).toHaveURL(/\/rubrics\/.+/);
  await expect(page.getByTestId("rubric-question")).toBeVisible();
  await expect(page.getByTestId("calibration-card")).toBeVisible();
});

test("migration: renders the picker and its empty state", async ({ page, seeded }) => {
  const agent = await seeded.agent();
  await page.goto(`/agents/${agent.id}/migration`);
  await expect(page.getByRole("heading", { level: 1, name: /model migration/ })).toBeVisible();
  await expect(page.getByTestId("pair-picker")).toBeVisible();
  await expect(page.getByText("Choose two versions")).toBeVisible();
});

test("scorecard: shows the agent's scorecard", async ({ page, seeded }) => {
  const agent = await seeded.agent();
  await page.goto(`/agents/${agent.id}/scorecard`);
  await expect(page.getByRole("heading", { level: 1, name: /scorecard/ })).toBeVisible();
  await expect(page.getByTestId("scorecard")).toBeVisible();
  await expect(page.getByTestId("stat-pass-rate")).toContainText(/\d+%|n\/a/);
  await themed(page, "scorecard");
  await page.emulateMedia({ media: "print" });
  await expect(page.locator('[data-slot="sidebar-container"]')).toBeHidden();
});
