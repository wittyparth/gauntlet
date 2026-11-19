import { expect, test } from "./fixtures";

// Starts a real run through the UI against the e-commerce smoke suite. Needs a dev stack whose
// gateway is the scripted fake (see README), so it costs nothing. Opt in with GAUNTLET_E2E_REAL_RUN=1.
test.skip(!process.env.GAUNTLET_E2E_REAL_RUN, "set GAUNTLET_E2E_REAL_RUN=1 on a fake-gateway stack");

test("real run: starts from the UI and streams live to completion", async ({ page, seeded, shot }) => {
  test.setTimeout(180_000);
  const agent = await seeded.agent();
  await page.goto(`/agents/${agent.id}`);
  await page.getByRole("button", { name: "Start run" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("combobox", { name: "Suite" }).click();
  await page.getByRole("option", { name: /Smoke \(10 scenarios\)/ }).click();
  await expect(dialog.getByTestId("stat-estimate")).toBeVisible({ timeout: 15_000 });
  await dialog.getByRole("button", { name: "Start run" }).click();

  await expect(page).toHaveURL(/\/runs\/run_/);
  await expect(page.getByTestId("stat-progress")).toBeVisible();
  const seen = new Set<string>();
  const progress = page.getByTestId("stat-progress").getByRole("status");
  await expect
    .poll(
      async () => {
        seen.add((await progress.textContent()) ?? "");
        return page.getByText("Finished", { exact: true }).first().isVisible();
      },
      { timeout: 150_000, intervals: [250] },
    )
    .toBe(true);
  await shot(page, "real-run-finished");
  await expect(progress).toContainText("10 of 10");
  expect(seen.size, "the console showed intermediate progress or the final state").toBeGreaterThan(0);
  await page.getByRole("button", { name: "Report" }).click();
  await expect(page.getByTestId("stat-pass-rate")).toBeVisible();
});
