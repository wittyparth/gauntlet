import { expect, test } from "./fixtures";

const STUDY = {
  name: "dva_recall",
  version: 1,
  seed: 7,
  platform_version: "1.0.0",
  started_at: "2026-11-20T10:00:00Z",
  smoke: false,
  metrics: { recall: 0.62, false_positives: 0 },
  intervals: { recall: [0.51, 0.72] },
  n: 120,
  limitations: ["Only the three DVA agents were scanned."],
  notes: "",
};

test("benchmarks: renders intervals and limitations", async ({ page }) => {
  await page.route("**/api/gauntlet/v1/meta/benchmarks", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ studies: [STUDY] }) }),
  );
  await page.goto("/benchmarks");
  await expect(page.getByRole("heading", { level: 1, name: "Benchmarks" })).toBeVisible();
  const card = page.getByTestId("study-dva_recall");
  await expect(card).toContainText("n = 120");
  await expect(card.getByTestId("interval-recall")).toHaveText("[0.510, 0.720]");
  await expect(card.getByTestId("interval-false_positives")).toHaveText("no interval");
  await expect(card.getByTestId("limitations")).toContainText("Only the three DVA agents");
});

test("benchmarks: empty list is an empty state", async ({ page }) => {
  await page.route("**/api/gauntlet/v1/meta/benchmarks", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ studies: [] }) }),
  );
  await page.goto("/benchmarks");
  await expect(page.getByTestId("empty-state")).toContainText("No results published yet");
});

test("benchmarks: public, works without a session", async ({ browser }) => {
  const ctx = await browser.newContext({ storageState: { cookies: [], origins: [] } });
  const page = await ctx.newPage();
  await page.route("**/api/gauntlet/v1/meta/benchmarks", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ studies: [STUDY] }) }),
  );
  await page.goto("http://localhost:3000/benchmarks");
  await expect(page.getByTestId("study-dva_recall")).toBeVisible();
  await ctx.close();
});
