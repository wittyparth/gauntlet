import { errorEnvelope, expect, test } from "./fixtures";

test("scenario viewer: shows seeded data", async ({ page, seeded, shot }) => {
  const scn = await seeded.scenario();
  await page.goto(`/scenarios/${scn.id}`);
  await expect(page.getByRole("heading", { level: 1, name: scn.scenario.title })).toBeVisible();
  await expect(page.getByText(scn.scenario.goal).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: /Success/ }).or(page.getByText("Success (must hold)"))).toBeVisible();
  await expect(page.getByTestId("check-node").first()).toBeVisible();
  await shot(page, "scenario-viewer");
  await page.getByRole("tab", { name: "JSON" }).click();
  await expect(page.getByText(`"id": "${scn.id}"`)).toBeVisible();
});

test("scenario viewer: not found", async ({ page, consoleErrors }) => {
  await page.route("**/api/gauntlet/v1/scenarios/scn_missing", (r) => r.fulfill(errorEnvelope(404, "not_found", "scenario not found")));
  await page.goto("/scenarios/scn_missing");
  await expect(page.getByText("Scenario not found")).toBeVisible();
  consoleErrors.splice(0);
});
