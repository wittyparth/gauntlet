import { errorEnvelope, expect, test } from "./fixtures";
import { REMOTE_AGENT, SQL_AGENT } from "./seed-security";

test("campaign launch: requires confirmation", async ({ page, seeded, shot, consoleErrors }) => {
  const f = await seeded.sqlAgentVersion();
  let body: Record<string, unknown> | null = null;
  await page.route("**/api/gauntlet/v1/campaigns", async (route) => {
    body = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ campaign_id: "run_mock_campaign", run: { id: "run_mock_campaign" }, attack_count: 6, skipped: [] }),
    });
  });
  await page.goto(`/security/campaigns/new?version=${f.agent_version_id}`);
  await expect(page.getByRole("heading", { level: 1, name: "Launch campaign" })).toBeVisible();
  await expect(page.getByTestId("category-list")).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Agent version" })).toContainText(SQL_AGENT);
  await expect(page.getByRole("combobox", { name: "Benign suite" })).toContainText("DVA SQL benign");
  await expect(page.getByTestId("stat-attacks")).toBeVisible();
  await expect(page.getByTestId("kill-switch")).toContainText("Off: attacks allowed");
  await page.waitForTimeout(500);
  await shot(page, "campaign-launch-golden");

  await page.getByLabel("Max attacks").fill("6");
  await page.getByRole("button", { name: "Review and launch" }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText(SQL_AGENT);
  const launch = dialog.getByRole("button", { name: "Launch campaign" });
  await expect(launch).toBeDisabled();
  await dialog.getByLabel(/Type/).fill("wrong name");
  await expect(launch).toBeDisabled();
  await dialog.getByLabel(/Type/).fill(SQL_AGENT);
  await shot(page, "campaign-launch-confirm");
  await launch.click();
  await expect(page).toHaveURL(/\/runs\/run_mock_campaign/);
  expect(body).toMatchObject({ world_id: "dva_sql", max_attacks: 6, mode: "static", budget_usd_micros: 2_000_000 });
  consoleErrors.splice(0); // the mocked run does not exist, so the console 404s
});

test("campaign launch: unverified remote target is disabled", async ({ page, seeded, shot }) => {
  await seeded.finding();
  await page.goto("/security/campaigns/new");
  await expect(page.getByTestId("unverified-alert")).toContainText(REMOTE_AGENT);
  await page.getByRole("combobox", { name: "Agent version" }).click();
  const option = page.getByRole("option", { name: /Remote agent/ });
  await expect(option).toHaveAttribute("aria-disabled", "true");
  await option.hover({ force: true });
  await expect(page.getByText(/has not passed ownership verification/)).toBeVisible();
  await shot(page, "campaign-launch-unverified");
});

test("campaign launch: engaged kill switch blocks the launch", async ({ page, seeded, shot }) => {
  await seeded.finding();
  await page.route("**/api/gauntlet/v1/killswitch", (r) =>
    r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        engaged: true,
        switches: [{ id: "ks_1", scope: "workspace", run_id: null, reason: "incident 42", engaged_by: "dev", engaged_at: new Date().toISOString() }],
      }),
    }),
  );
  await page.goto("/security/campaigns/new");
  await expect(page.getByTestId("killswitch-block")).toBeVisible();
  await expect(page.getByTestId("kill-switch")).toContainText("incident 42");
  await expect(page.getByRole("button", { name: "Review and launch" })).toBeDisabled();
  await shot(page, "campaign-launch-killswitch");
});

test("campaign launch: empty selection, loading and error states", async ({ page, seeded, shot, consoleErrors }) => {
  const f = await seeded.sqlAgentVersion();
  const url = `/security/campaigns/new?version=${f.agent_version_id}`;
  await page.goto(url);
  await expect(page.getByTestId("category-list")).toBeVisible();
  await page.getByRole("button", { name: "Clear" }).click();
  await page.getByRole("button", { name: "Review and launch" }).click();
  await expect(page.getByText("Choose at least one attack category")).toBeVisible();
  await shot(page, "campaign-launch-empty");

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await page.route("**/api/gauntlet/v1/campaigns", async (r) => {
    await new Promise((res) => setTimeout(res, 300));
    await r.fulfill(errorEnvelope(403, "target_not_verified", "target host 'dva-sql' is not verified"));
  });
  await page.goto(url);
  await expect(page.getByTestId("category-list")).toBeVisible();
  await page.getByRole("button", { name: "Review and launch" }).click();
  const dialog = page.getByRole("alertdialog");
  await dialog.getByLabel(/Type/).fill(SQL_AGENT);
  await dialog.getByRole("button", { name: "Launch campaign" }).click();
  await expect(page.getByText("target host 'dva-sql' is not verified").first()).toBeVisible();
  await shot(page, "campaign-launch-error");
  consoleErrors.splice(0);
});

// Starts a real campaign through the UI against the DVA SQL agent. The fake gateway runs it, so it
// costs nothing. Opt in with GAUNTLET_E2E_REAL_RUN=1 on a stack with the compose `dva` profile.
test("campaign launch: a real campaign produces findings", async ({ page, seeded, shot }) => {
  test.skip(!process.env.GAUNTLET_E2E_REAL_RUN, "set GAUNTLET_E2E_REAL_RUN=1 on a fake-gateway stack with dva-sql");
  test.setTimeout(180_000);
  const f = await seeded.finding();
  await page.goto(`/security/campaigns/new?version=${f.agent_version_id}`);
  await expect(page.getByTestId("category-list")).toBeVisible();
  await page.getByRole("button", { name: "Clear" }).click();
  await page.getByRole("checkbox", { name: /Injection through tools/ }).check();
  await page.getByLabel("Max attacks").fill("4");
  await page.getByRole("button", { name: "Review and launch" }).click();
  const dialog = page.getByRole("alertdialog");
  await dialog.getByLabel(/Type/).fill(SQL_AGENT);
  await dialog.getByRole("button", { name: "Launch campaign" }).click();
  await expect(page).toHaveURL(/\/runs\/run_/);
  await expect(page.getByText("Finished", { exact: true }).first()).toBeVisible({ timeout: 150_000 });
  await shot(page, "campaign-launch-run-finished");
  await page.goto("/findings");
  await expect(page.getByTestId("finding-row").first()).toBeVisible();
});

test("campaign launch: advanced attack ids and inject target are sent (mocked POST)", async ({ page, seeded, consoleErrors }) => {
  const f = await seeded.finding();
  let body: Record<string, unknown> | null = null;
  await page.route("**/api/gauntlet/v1/campaigns", async (route) => {
    body = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ campaign_id: "run_mock_adv", run: { id: "run_mock_adv" }, attack_count: 1, skipped: [] }),
    });
  });
  await page.goto(`/security/campaigns/new?version=${f.agent_version_id}`);
  await expect(page.getByTestId("category-list")).toBeVisible();
  await page.getByTestId("advanced").getByText("Advanced", { exact: true }).click();
  await page.getByLabel("Attack ids").fill("atk_does_not_exist");
  await expect(page.getByText(/Not in the library: atk_does_not_exist/)).toBeVisible();
  await page.getByLabel("Attack ids").fill("");
  await page.getByLabel("Injection target").fill("orders/ord_1001/notes");
  await page.getByRole("button", { name: "Review and launch" }).click();
  const dialog = page.getByRole("alertdialog");
  await dialog.getByLabel(/Type/).fill((await dialog.locator("span.font-mono").first().innerText()).trim());
  await dialog.getByRole("button", { name: "Launch campaign" }).click();
  await expect(page).toHaveURL(/\/runs\/run_mock_adv/);
  expect(body).toMatchObject({ inject_target: "orders/ord_1001/notes" });
  consoleErrors.splice(0);
});
