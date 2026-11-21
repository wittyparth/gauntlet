import { errorEnvelope, expect, test } from "./fixtures";

test("audit log: shows seeded data", async ({ page, seeded, shot }) => {
  await seeded.finding();
  await page.goto("/security/audit");
  await expect(page.getByRole("heading", { level: 1, name: "Audit log" })).toBeVisible();
  await expect(page.getByTestId("chain-ok")).toBeVisible();
  const rows = page.getByTestId("audit-row");
  await expect(rows.first()).toBeVisible();
  await expect(page.getByText("attack_run.created").first()).toBeVisible();
  await shot(page, "audit-log-golden");

  await page.getByLabel("Any action").click();
  await page.getByRole("option", { name: "attack_run.created" }).click();
  await expect(page).toHaveURL(/action=attack_run.created/);
  await expect(rows.first()).toContainText("attack_run.created");
});

test("audit log: empty, loading and error states", async ({ page, shot, consoleErrors }) => {
  await page.route("**/api/gauntlet/v1/audit?*", async (r) => {
    await new Promise((res) => setTimeout(res, 1200));
    await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [] }) });
  });
  await page.goto("/security/audit");
  await expect(page.getByTestId("loading-rows")).toBeVisible();
  await shot(page, "audit-log-loading");
  await expect(page.getByTestId("empty-state")).toContainText("Nothing recorded yet");
  await shot(page, "audit-log-empty");

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await page.route("**/api/gauntlet/v1/audit?*", (r) => r.fulfill(errorEnvelope(500)));
  await page.reload();
  await expect(page.getByTestId("error-state").first()).toBeVisible();
  await shot(page, "audit-log-error");
  consoleErrors.splice(0);
});
