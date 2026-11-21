import { mkdirSync } from "node:fs";
import path from "node:path";

import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";

/**
 * GUARD: e2e must never start runs. The compose worker holds live model keys, so a run started here
 * spends real money. The compare pair is seeded by POST /v1/dev/seed (two finished scripted runs).
 */
async function runPair(request: import("@playwright/test").APIRequestContext) {
  const seeded = await request.post("/api/gauntlet/v1/dev/seed", { data: { reset: false, compare_run: true } });
  expect(seeded.ok()).toBeTruthy();
  const s = (await seeded.json()) as { run_id: string; compare_run_id: string };
  return { base: { id: s.run_id }, cand: { id: s.compare_run_id } };
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
  const pair = await runPair(request);
  await page.goto(`/runs/${pair.cand.id}/compare?baseline=${pair.base.id}`);
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
