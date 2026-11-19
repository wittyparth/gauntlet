import { errorEnvelope, expect, test } from "./fixtures";

test("scenarios: shows seeded data", async ({ page, seeded, shot }) => {
  const scn = await seeded.scenario();
  await page.goto("/scenarios");
  await expect(page.getByRole("heading", { level: 1, name: "Scenarios" })).toBeVisible();
  await expect(page.getByTestId("scenario-row").first()).toBeVisible();
  const total = await page.getByTestId("scenario-row").count();
  await shot(page, "scenarios");
  const fragment = scn.scenario.title.split(" ")[0];
  await page.getByLabel("Search title or goal").fill(scn.scenario.title);
  await expect(page.getByTestId("scenario-row").first()).toContainText(fragment);
  expect(await page.getByTestId("scenario-row").count()).toBeLessThanOrEqual(total);
});

test("scenarios: the Draft filter shows only drafts", async ({ page }) => {
  await page.route("**/api/gauntlet/v1/scenarios*", async (r) => {
    const res = await r.fetch();
    const body = await res.json();
    body.items[0].status = "draft";
    await r.fulfill({ response: res, json: body });
  });
  await page.goto("/scenarios");
  await page.getByRole("button", { name: "Draft" }).click();
  await expect(page).toHaveURL(/status=draft/);
  const rows = page.getByTestId("scenario-row");
  await expect(rows.first()).toBeVisible();
  const n = await rows.count();
  for (let i = 0; i < n; i++) await expect(rows.nth(i)).toContainText("Draft");
});

test("scenarios: empty and filtered-empty states", async ({ page }) => {
  await page.goto("/scenarios?q=zzzz-no-such-scenario");
  await expect(page.getByText("No scenarios match these filters")).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByTestId("scenario-row").first()).toBeVisible();
  await page.route("**/api/gauntlet/v1/scenarios*", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], next_cursor: null }) }));
  await page.goto("/scenarios");
  await expect(page.getByText("No scenarios yet")).toBeVisible();
});

test("scenarios: error state", async ({ page, consoleErrors }) => {
  await page.route("**/api/gauntlet/v1/scenarios*", (r) => r.fulfill(errorEnvelope(500)));
  await page.goto("/scenarios");
  await expect(page.getByTestId("error-state")).toBeVisible();
  consoleErrors.splice(0);
});
