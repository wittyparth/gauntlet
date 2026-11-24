import { errorEnvelope, expect, test } from "./fixtures";

test("findings: shows seeded data", async ({ page, seeded, shot }) => {
  await seeded.finding();
  await page.goto("/findings");
  await expect(page.getByRole("heading", { level: 1, name: "Findings" })).toBeVisible();
  const rows = page.getByTestId("finding-row");
  await expect(rows.first()).toBeVisible();
  await expect(rows.first().getByText(/High|Critical|Medium|Low/).first()).toBeVisible();
  await expect(rows.first()).toContainText(/\d+\/\d+/);
  await shot(page, "findings-golden");

  // The status facet narrows the list: nothing is fixed yet.
  await page.getByRole("button", { name: "Fixed" }).click();
  await expect(page).toHaveURL(/status=fixed/);
  await expect(page.getByTestId("empty-state")).toContainText("No findings match these filters");
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(rows.first()).toBeVisible();

  // Row opens the detail.
  await rows.first().click();
  await expect(page).toHaveURL(/\/findings\/fnd_/);
});

test("findings: filters by severity from the URL and searches", async ({ page, seeded }) => {
  await seeded.finding();
  // A severity no finding has, whatever the dev database already holds.
  const all = (await (await page.request.get("/api/gauntlet/v1/findings?limit=200")).json()).items as { severity: string }[];
  const present = new Set(all.map((f) => f.severity));
  const absent = ["critical", "high", "medium", "low"].find((sev) => !present.has(sev));
  test.skip(!absent, "every severity has a finding in this database");
  await page.goto(`/findings?severity=${absent}`);
  await expect(page.getByTestId("empty-state")).toContainText("No findings match these filters");
  await page.goto("/findings");
  await page.getByLabel("Search findings").fill("zzz-no-such-finding");
  await expect(page.getByTestId("empty-state")).toBeVisible();
});

test("findings: empty, loading and error states", async ({ page, shot, consoleErrors }) => {
  await page.route("**/api/gauntlet/v1/findings?*", async (r) => {
    await new Promise((res) => setTimeout(res, 1200));
    await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], next_cursor: null }) });
  });
  await page.goto("/findings");
  await expect(page.getByTestId("loading-rows")).toBeVisible();
  await shot(page, "findings-loading");
  await expect(page.getByTestId("empty-state")).toContainText("No findings. Launch a campaign to look for some.");
  await shot(page, "findings-empty");

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await page.route("**/api/gauntlet/v1/findings?*", (r) => r.fulfill(errorEnvelope(500)));
  await page.reload();
  await expect(page.getByTestId("error-state")).toBeVisible();
  await shot(page, "findings-error");
  consoleErrors.splice(0);
});
