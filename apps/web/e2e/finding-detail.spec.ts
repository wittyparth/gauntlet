import { errorEnvelope, expect, test } from "./fixtures";

test("finding detail: shows seeded data", async ({ page, seeded, shot }) => {
  const f = await seeded.finding();
  await page.goto(`/findings/${f.id}`);
  await expect(page.getByRole("heading", { level: 1, name: f.title })).toBeVisible();
  await expect(page.getByTestId("repro")).toContainText(/\d+\s*(of|\/)\s*\d+/);
  const reproducer = page.getByTestId("reproducer-card");
  await expect(reproducer.getByTestId("check-node").first()).toBeVisible();
  await expect(reproducer.getByTestId("attack-payload")).toBeVisible();

  // The cited event is selected in the evidence transcript and its quote is highlighted.
  const transcript = page.getByTestId("evidence-transcript");
  await expect(transcript.locator('[data-testid^="event-"]').first()).toBeVisible();
  // The cited event is the selected, highlighted row (a tool call here; message quotes are marked too).
  await expect(transcript.locator('[data-selected="true"]')).toBeVisible();
  await page.waitForTimeout(500);
  await shot(page, "finding-detail-golden");

  // One click from the finding to the exact cited event in the episode viewer.
  await page.getByRole("link", { name: /Open episode/ }).click();
  await expect(page).toHaveURL(/\/episodes\/ep_[^#]+#e-\d+/);
});

test("finding detail: changing status sends the update", async ({ page, seeded }) => {
  const f = await seeded.finding();
  let sent: { status?: string } | null = null;
  const current = (await (await page.request.get(`/api/gauntlet/v1/findings/${f.id}`)).json()) as Record<string, unknown>;
  await page.route(`**/api/gauntlet/v1/findings/${f.id}`, async (route) => {
    if (route.request().method() !== "PATCH") return route.fallback();
    sent = route.request().postDataJSON() as { status?: string };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...current, status: sent.status }) });
  });
  await page.goto(`/findings/${f.id}`);
  await page.getByTestId("status-menu").click();
  await page.getByRole("menuitemradio", { name: "Triaged" }).click();
  await expect.poll(() => sent?.status).toBe("triaged");
});

test("finding detail: a rejected transition rolls back and says why", async ({ page, seeded, consoleErrors }) => {
  const f = await seeded.finding();
  await page.route(`**/api/gauntlet/v1/findings/${f.id}`, async (route) => {
    if (route.request().method() !== "PATCH") return route.fallback();
    await route.fulfill(errorEnvelope(409, "illegal_transition", "cannot move from open to verified"));
  });
  await page.goto(`/findings/${f.id}`);
  const before = await page.getByTestId("status-menu").textContent();
  await page.getByTestId("status-menu").click();
  await page.getByRole("menuitemradio", { name: "Verified" }).click();
  await expect(page.getByText("cannot move from open to verified")).toBeVisible();
  await expect(page.getByTestId("status-menu")).toHaveText(before ?? "");
  await page.unrouteAll({ behavior: "ignoreErrors" });
  consoleErrors.splice(0); // the browser logs the expected 409 as a resource error
});

test("finding detail: exports download and replay starts a run", async ({ page, seeded, consoleErrors }) => {
  const f = await seeded.finding();
  await page.goto(`/findings/${f.id}`);
  await page.getByRole("button", { name: "Finding actions" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("menuitem", { name: "Markdown report" }).click();
  expect((await download).suggestedFilename()).toBe(`${f.id}.md`);

  await page.route(`**/api/gauntlet/v1/findings/${f.id}/replay`, (r) =>
    r.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: "run_mock_replay" }) }),
  );
  await page.getByRole("button", { name: "Finding actions" }).click();
  await page.getByRole("menuitem", { name: /Replay/ }).click();
  await expect(page).toHaveURL(/\/runs\/run_mock_replay/);
  consoleErrors.splice(0); // the mocked run does not exist, so the console 404s
});

test("finding detail: not found, loading and error states", async ({ page, seeded, shot, consoleErrors }) => {
  const f = await seeded.finding();
  await page.route(`**/api/gauntlet/v1/findings/${f.id}`, async (r) => {
    await new Promise((res) => setTimeout(res, 1200));
    await r.continue();
  });
  await page.goto(`/findings/${f.id}`);
  await expect(page.getByTestId("loading-card").first()).toBeVisible();
  await shot(page, "finding-detail-loading");
  await expect(page.getByRole("heading", { level: 1, name: f.title })).toBeVisible();

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await page.goto("/findings/fnd_does_not_exist");
  await expect(page.getByTestId("empty-state")).toContainText("Finding not found");
  await shot(page, "finding-detail-404");

  await page.route(`**/api/gauntlet/v1/findings/${f.id}`, (r) => r.fulfill(errorEnvelope(500)));
  await page.goto(`/findings/${f.id}`);
  await expect(page.getByTestId("error-state")).toBeVisible();
  await shot(page, "finding-detail-error");
  consoleErrors.splice(0);
});
