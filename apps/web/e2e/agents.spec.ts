import { errorEnvelope, expect, test } from "./fixtures";

test("agents: shows seeded data", async ({ page, seeded, shot }) => {
  const agent = await seeded.agent();
  await page.goto("/agents");
  await expect(page.getByRole("heading", { level: 1, name: "Agents" })).toBeVisible();
  await expect(page.getByTestId("agent-row").filter({ hasText: agent.name }).first()).toBeVisible();
  await expect(page.getByTestId("agent-row").filter({ hasText: "Customer support for an online outdoor gear store" }).first()).toBeVisible();
  await shot(page, "agents");
  await page.getByTestId("agent-row").filter({ hasText: agent.name }).first().click();
  await expect(page).toHaveURL(new RegExp(`/agents/${agent.id}`));
});

test("agents: empty state", async ({ page }) => {
  await page.route("**/api/gauntlet/v1/agents*", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], next_cursor: null }) }));
  await page.goto("/agents");
  await expect(page.getByText("No agents yet")).toBeVisible();
  await expect(page.getByRole("link", { name: "Set up your first agent" })).toBeVisible();
});

test("agents: error state", async ({ page, consoleErrors }) => {
  await page.route("**/api/gauntlet/v1/agents*", (r) => r.fulfill(errorEnvelope(500)));
  await page.goto("/agents");
  await expect(page.getByTestId("error-state")).toContainText("internal error");
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  consoleErrors.splice(0);
});

test("agents: loading state", async ({ page, shot }) => {
  await page.route("**/api/gauntlet/v1/agents*", async (r) => {
    await new Promise((res) => setTimeout(res, 1500));
    await r.continue();
  });
  await page.goto("/agents");
  await expect(page.getByTestId("loading-rows")).toBeVisible();
  await shot(page, "agents-loading");
});
