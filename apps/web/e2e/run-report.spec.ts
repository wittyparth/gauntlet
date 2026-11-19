import { errorEnvelope, expect, test } from "./fixtures";

test("run report: shows seeded data", async ({ page, seeded, shot }) => {
  const run = await seeded.run();
  await page.goto(`/runs/${run.id}/report`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByTestId("stat-pass-rate")).toContainText(/\d+%/);
  await expect(page.getByTestId("scenario-row").first()).toBeVisible();
  await expect(page.getByTestId("failure-row").first()).toBeVisible();
  await shot(page, "run-report");
  await page.getByTestId("failure-row").first().click();
  await expect(page).toHaveURL(/\/episodes\/ep_/);
});

test("run report: error state", async ({ page, seeded, consoleErrors }) => {
  const run = await seeded.run();
  await page.route(`**/api/gauntlet/v1/runs/${run.id}/report`, (r) => r.fulfill(errorEnvelope(500)));
  await page.goto(`/runs/${run.id}/report`);
  await expect(page.getByTestId("error-state")).toBeVisible();
  consoleErrors.splice(0);
});
