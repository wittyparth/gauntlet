import { errorEnvelope, expect, test } from "./fixtures";

test("agent overview: shows seeded data", async ({ page, seeded, shot }) => {
  const agent = await seeded.agent();
  await page.goto(`/agents/${agent.id}`);
  await expect(page.getByRole("heading", { level: 1, name: agent.name })).toBeVisible();
  for (const name of ["Profile", "Target", /^Tools/, "Recent runs"]) {
    await expect(page.getByRole("heading", { name })).toBeVisible();
  }
  await expect(page.getByTestId("tool-row").first()).toBeVisible();
  await expect(page.getByTestId("tool-row").first().getByText(/read|write|financial|destructive/).first()).toBeVisible();
  await shot(page, "agent-overview");
  await page.getByTestId("recent-run").first().click();
  await expect(page).toHaveURL(/\/runs\/run_/);
});

test("agent overview: start run dialog shows an estimate", async ({ page, seeded }) => {
  const agent = await seeded.agent();
  await page.goto(`/agents/${agent.id}`);
  await page.getByRole("button", { name: "Start run" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByTestId("stat-estimate")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
});

test("agent overview: not found", async ({ page, consoleErrors }) => {
  await page.route("**/api/gauntlet/v1/agents/agt_missing*", (r) => r.fulfill(errorEnvelope(404, "not_found", "agent not found")));
  await page.goto("/agents/agt_missing");
  await expect(page.getByText("Agent not found")).toBeVisible();
  consoleErrors.splice(0);
});
