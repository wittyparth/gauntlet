import { expect, test } from "@playwright/test";

test.use({ storageState: { cookies: [], origins: [] } });

test("landing: title, Fig. 1 film with captions, and the calls to action", async ({ page }) => {
  await page.goto("/landing");
  await expect(page).toHaveTitle(/Gauntlet/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Test, attack, and guard your");

  const film = page.locator("video");
  await expect(film).toBeVisible();
  await expect(film).toHaveAttribute("preload", "none");
  await expect(film.locator("track[kind='captions']")).toHaveAttribute("src", "/media/gauntlet-tour.vtt");

  await expect(page.getByRole("button", { name: "Watch the film (2:49)" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Try the arena" }).first()).toHaveAttribute("href", "/arena");
  await expect(page.getByRole("link", { name: "Console" }).first()).toHaveAttribute("href", "/login");
  await expect(page.getByRole("link", { name: "Open the benchmarks" })).toHaveAttribute("href", "/benchmarks");
  await expect(page.getByRole("table")).toContainText("Table 1.");
});
