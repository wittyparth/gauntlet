import { errorEnvelope, expect, test } from "./fixtures";

test("security posture: shows seeded data", async ({ page, seeded, shot }) => {
  const f = await seeded.finding();
  await page.goto(`/security?version=${f.agent_version_id}`);
  await expect(page.getByRole("heading", { level: 1, name: "Security posture" })).toBeVisible();
  await expect(page.getByTestId("grade")).toHaveText(/^[A-F]$/);
  await expect(page.getByTestId("stat-attacks-run")).toBeVisible();
  await expect(page.getByTestId("kill-switch")).toContainText("Off: attacks allowed");
  await expect(page.getByTestId("ownership")).toBeVisible();

  const heatmap = page.getByTestId("coverage-heatmap");
  await expect(heatmap.getByTestId("heat-row").first()).toBeVisible();
  await expect(heatmap.locator('[data-testid="heat-cell"][data-state="tested"]').first()).toBeVisible();
  await expect(heatmap.locator('[data-testid="heat-cell"][data-state="untested"]').first()).toContainText("not tested");
  await expect(page.getByTestId("tool-permissions").getByTestId("tool-row").first()).toBeVisible();
  await page.waitForTimeout(500);
  await shot(page, "security-posture-golden");

  // A heat cell with successes opens the inbox filtered to its category.
  await heatmap.locator('[data-state="tested"] a').first().click();
  await expect(page).toHaveURL(/\/findings\?category=/);
  await expect(page.getByTestId("finding-row").first()).toBeVisible();

  // Top findings link to the detail.
  await page.goto(`/security?version=${f.agent_version_id}`);
  await page.getByTestId("top-finding").first().click();
  await expect(page).toHaveURL(/\/findings\/fnd_/);
});

test("security posture: heatmap in the light theme and with reduced motion", async ({ page, seeded, shot }) => {
  const f = await seeded.finding();
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "light" });
  await page.goto(`/security?version=${f.agent_version_id}`);
  await page.evaluate(() => document.documentElement.classList.remove("dark"));
  await expect(page.getByTestId("coverage-heatmap")).toBeVisible();
  await page.waitForTimeout(400);
  await shot(page, "security-posture-light");
});

test("security posture: no attack runs, loading and error states", async ({ page, seeded, shot, consoleErrors }) => {
  const f = await seeded.finding();
  const agents = (await (await page.request.get("/api/gauntlet/v1/agents?limit=200")).json()).items as { id: string }[];
  const url = new RegExp(`/api/gauntlet/v1/agents/[^/]+/versions/${f.agent_version_id}/posture`);
  const posture = (await (await page.request.get(`/api/gauntlet/v1/agents/${agents.find(Boolean)?.id}/versions/${f.agent_version_id}/posture`)).json().catch(() => null)) as Record<string, unknown> | null;

  await page.route(url, async (r) => {
    await new Promise((res) => setTimeout(res, 1200));
    await r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...(posture ?? {}),
        agent_version_id: f.agent_version_id,
        summary: { open_by_severity: {}, verified: 0, accepted_risk: 0, attacks_run: 0, attack_success_rate: 0 },
      }),
    });
  });
  await page.goto(`/security?version=${f.agent_version_id}`);
  await expect(page.getByTestId("loading-card").first()).toBeVisible();
  await shot(page, "security-posture-loading");
  await expect(page.getByTestId("empty-state")).toContainText("No attack runs for this version yet");
  await shot(page, "security-posture-empty");

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await page.route(url, (r) => r.fulfill(errorEnvelope(500)));
  await page.reload();
  await expect(page.getByTestId("error-state")).toBeVisible();
  await shot(page, "security-posture-error");
  consoleErrors.splice(0);
});

test("security posture: the kill switch can be engaged and released", async ({ page, seeded }) => {
  const f = await seeded.finding();
  await page.goto(`/security?version=${f.agent_version_id}`);
  await page.getByRole("button", { name: "Engage kill switch" }).click();
  const dialog = page.getByRole("alertdialog");
  const confirm = dialog.getByRole("button", { name: "Engage kill switch" });
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel("Reason").fill("e2e kill switch check");
  await confirm.click();
  const card = page.getByTestId("kill-switch");
  await expect(card).toContainText("Engaged");
  await expect(card).toContainText("e2e kill switch check");
  await card.getByRole("button", { name: "Release" }).click();
  await expect(card).toContainText("Off: attacks allowed");
});
