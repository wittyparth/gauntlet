import { errorEnvelope, expect, test } from "./fixtures";

test("states: episode viewer evidence highlight, narrow width and reduced motion", async ({ page, seeded, shot }) => {
  const ep = await seeded.failedEpisode();
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "dark" });
  await page.goto(`/episodes/${ep.id}`);
  await page.getByTestId("evidence-quote").first().click();
  await expect(page.locator('[data-selected="true"]')).toBeVisible();
  await page.waitForTimeout(600);
  await shot(page, "episode-viewer-evidence");
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.waitForTimeout(300);
  await shot(page, "episode-viewer-1024");
  await page.setViewportSize({ width: 900, height: 768 });
  await page.getByRole("button", { name: "Details" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.waitForTimeout(400);
  await shot(page, "episode-viewer-sheet");
});

test("states: episode viewer in the light theme", async ({ page, seeded, shot }) => {
  const ep = await seeded.failedEpisode();
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto(`/episodes/${ep.id}`);
  await page.evaluate(() => {
    document.documentElement.classList.remove("dark");
  });
  await expect(page.getByTestId("verdict-card").first()).toBeVisible();
  await page.waitForTimeout(400);
  await shot(page, "episode-viewer-light");
});

test("states: episode viewer loading and error", async ({ page, seeded, shot, consoleErrors }) => {
  const ep = await seeded.failedEpisode();
  await page.route(`**/api/gauntlet/v1/episodes/${ep.id}*`, async (r) => {
    await new Promise((res) => setTimeout(res, 1500));
    await r.continue();
  });
  await page.goto(`/episodes/${ep.id}`);
  await expect(page.getByRole("heading", { level: 1, name: "Episode" })).toBeAttached();
  await shot(page, "episode-viewer-loading");
  await page.unrouteAll({ behavior: "ignoreErrors" });
  await page.route(`**/api/gauntlet/v1/episodes/${ep.id}*`, (r) => r.fulfill(errorEnvelope(500)));
  await page.reload();
  await expect(page.getByTestId("error-state")).toBeVisible();
  await shot(page, "episode-viewer-error");
  consoleErrors.splice(0);
});

test("states: onboarding target step with a slider value", async ({ page, shot }) => {
  await page.goto("/onboarding");
  await page.getByLabel("Name").fill("State probe");
  await page.getByLabel("Purpose").fill("Probe");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("How should Gauntlet reach it?")).toBeVisible();
  await page.getByRole("slider").focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await page.getByRole("button", { name: "HTTP" }).click();
  await shot(page, "onboarding-2-http");
});
