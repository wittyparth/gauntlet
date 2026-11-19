import { expect, test } from "./fixtures";
import { mockLiveRun, RUN_ID } from "./mocks";

test("run console: shows seeded data", async ({ page, seeded, shot }) => {
  const run = await seeded.run();
  await page.goto(`/runs/${run.id}`);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(run.suite_id);
  await expect(page.getByTestId("stat-progress")).toBeVisible();
  await expect(page.getByTestId("stat-cost")).toBeVisible();
  const row = page.getByTestId("episode-row").first();
  await expect(row).toBeVisible();
  await row.click();
  await expect(page.getByTestId("event-0")).toBeVisible();
  await shot(page, "run-console");
  await page.getByRole("link", { name: /Open episode/ }).click();
  await expect(page).toHaveURL(/\/episodes\/ep_/);
});

test("run console: updates live", async ({ page, shot }) => {
  await mockLiveRun(page);
  await page.goto(`/runs/${RUN_ID}`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  // Snapshot A, then the scripted stream rings the doorbell and REST serves snapshot B.
  await expect(page.getByTestId("stat-progress")).toContainText("11 of 30");
  await expect(page.getByTestId("event-3")).toBeVisible();
  await expect(page.getByTestId("stat-cost")).toContainText("0.33");
  await shot(page, "run-console-live");
});

test("run console: cancel asks for confirmation", async ({ page }) => {
  await mockLiveRun(page);
  const cancels: string[] = [];
  await page.route(`**/api/gauntlet/v1/runs/${RUN_ID}/cancel`, (r) => {
    cancels.push(r.request().method());
    return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: RUN_ID, status: "cancelled" }) });
  });
  await page.goto(`/runs/${RUN_ID}`);
  await page.getByRole("button", { name: "Cancel" }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toBeVisible();
  expect(cancels).toEqual([]);
  await dialog.getByRole("button", { name: "Cancel run" }).click();
  await expect.poll(() => cancels).toEqual(["POST"]);
});

test("run console: empty run", async ({ page }) => {
  await page.route(`**/api/gauntlet/v1/runs/${RUN_ID}`, (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: RUN_ID, suite_id: "smoke", agent_version_id: "agv_demo", status: "queued", repetitions: 1, budget_usd_micros: 2000000, spent_usd_micros: 0, reserved_usd_micros: 0, counts: { total: 0, queued: 0, leased: 0, done: 0, cancelled: 0, by_outcome: {} }, created_at: new Date().toISOString(), finished_at: null }) }),
  );
  await page.route(`**/api/gauntlet/v1/runs/${RUN_ID}/episodes*`, (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], next_cursor: null }) }));
  await page.route(`**/api/gauntlet/v1/runs/${RUN_ID}/stream`, (r) => r.fulfill({ status: 200, headers: { "content-type": "text/event-stream" }, body: "" }));
  await page.goto(`/runs/${RUN_ID}`);
  await expect(page.getByText("Episodes are being queued")).toBeVisible();
});
