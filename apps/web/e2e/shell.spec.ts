import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";

const nav = (page: Page, name: string) => page.locator("[data-sidebar=menu-button]", { hasText: name });

test("shell: navigates between sections", async ({ page, shot }) => {
  await page.goto("/agents");
  await expect(page.getByRole("heading", { level: 1, name: "Agents" })).toBeVisible();
  await nav(page, "Scenarios").click();
  await expect(page.getByRole("heading", { level: 1, name: "Scenarios" })).toBeVisible();
  await expect(nav(page, "Scenarios")).toHaveAttribute("aria-current", "page");
  await nav(page, "Runs").click();
  await expect(page.getByRole("heading", { level: 1, name: "Runs" })).toBeVisible();
  await expect(nav(page, "Runs")).toHaveAttribute("aria-current", "page");
  await shot(page, "shell");
});

test("shell: sign out returns to login", async ({ page }) => {
  await page.goto("/agents");
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
});
