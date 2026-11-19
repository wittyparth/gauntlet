import { expect, test } from "./fixtures";

test("runs: shows seeded data", async ({ page, seeded, shot }) => {
  await seeded.run();
  await page.goto("/runs");
  await expect(page.getByRole("heading", { level: 1, name: "Runs" })).toBeVisible();
  const row = page.getByTestId("run-row").first();
  await expect(row).toBeVisible();
  await shot(page, "runs");
  await row.click();
  await expect(page).toHaveURL(/\/runs\/run_/);
});

test("runs: empty state", async ({ page }) => {
  await page.route("**/api/gauntlet/v1/runs*", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], next_cursor: null }) }));
  await page.goto("/runs");
  await expect(page.getByText("No runs yet")).toBeVisible();
});
