import { expect, test } from "./fixtures";

test("onboarding: validates required fields", async ({ page }) => {
  let posts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().includes("/api/gauntlet/")) posts += 1;
  });
  await page.goto("/onboarding");
  await expect(page.getByRole("heading", { level: 1, name: "Set up your first agent" })).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Name the agent.")).toBeVisible();
  await expect(page.getByText("Say what the agent is for.")).toBeVisible();
  expect(posts).toBe(0);
});

test("onboarding: completes the pack path", async ({ page, shot, consoleErrors }) => {
  await page.goto("/onboarding");
  await page.getByLabel("Name").fill("E2E support agent");
  await page.getByLabel("Purpose").fill("Answers shop order questions");
  await page.getByLabel("Policies").fill("Only refund within 30 days.");
  await shot(page, "onboarding-1-agent");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByText("How should Gauntlet reach it?")).toBeVisible();
  await page.getByLabel("System prompt").fill("You are a support agent for a shop.");
  await page.getByRole("combobox", { name: "World" }).click();
  await page.getByRole("option", { name: "ecommerce" }).click();
  await expect(page.getByText(/tools in this world/)).toBeVisible();
  await shot(page, "onboarding-2-target");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByText("Which scenarios should it face?")).toBeVisible();
  await page.getByText("Smoke (10 scenarios)").click();
  await shot(page, "onboarding-3-scenarios");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByText("Ready to run")).toBeVisible();
  await expect(page.getByTestId("stat-estimate")).toBeVisible({ timeout: 10_000 });
  await shot(page, "onboarding-4-run");

  // No real run is started: the create call is mocked.
  await page.route("**/api/gauntlet/v1/runs", async (r) => {
    if (r.request().method() === "POST" && !r.request().url().includes("dry_run")) {
      await r.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: "run_mocked" }) });
    } else await r.fallback();
  });
  await page.getByRole("button", { name: "Start run" }).click();
  await expect(page).toHaveURL(/\/runs\/run_mocked/);
  consoleErrors.splice(0); // the mocked run id does not exist, so the console 404s
});
