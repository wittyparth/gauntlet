import { expect, test } from "./fixtures";

test.use({ storageState: { cookies: [], origins: [] } });

test("login: rejects a bad key", async ({ page, consoleErrors }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.getByLabel("API key").fill("gk_not_a_real_key");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.locator("#login-error")).toContainText("not accepted");
  await expect(page).toHaveURL(/\/login/);
  consoleErrors.splice(0); // the 401 is logged by the browser
});

test("login: accepts the seeded key", async ({ page, shot }) => {
  await page.goto("/login");
  await shot(page, "login");
  await page.getByLabel("API key").fill(process.env.GAUNTLET_E2E_API_KEY ?? "gk_dev_local_only");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/(agents|onboarding)/);
  await expect(page.locator("[data-sidebar=menu-button]", { hasText: "Agents" })).toBeVisible();
});

test("login: redirects to login without a session", async ({ page }) => {
  await page.goto("/runs");
  await expect(page).toHaveURL(/\/login\?next=%2Fruns/);
});
