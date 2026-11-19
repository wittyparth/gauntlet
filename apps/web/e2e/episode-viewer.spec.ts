import { errorEnvelope, expect, test } from "./fixtures";

test("episode viewer: shows seeded data", async ({ page, seeded, shot }) => {
  const ep = await seeded.failedEpisode();
  await page.goto(`/episodes/${ep.id}`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText("Failed", { exact: true }).first()).toBeVisible();
  await expect(page.getByTestId("event-0")).toBeVisible();
  await expect(page.locator('[data-testid^="event-"][data-kind="user_message"]').first()).toBeVisible();
  await expect(page.locator('[data-testid^="event-"][data-kind="agent_message"]').first()).toBeVisible();
  await expect(page.getByTestId("verdict-card").first()).toBeVisible();
  await shot(page, "episode-viewer");
  await page.getByRole("tab", { name: /Tools/ }).click();
  await expect(page.locator('[data-testid^="timeline-item-"]').first()).toBeVisible();
  await page.getByRole("tab", { name: /State/ }).click();
  await expect(page.getByTestId("diff-entry").first()).toBeVisible();
  await shot(page, "episode-viewer-state");
});

test("episode viewer: evidence scrolls to and highlights the cited event", async ({ page, seeded }) => {
  const ep = await seeded.failedEpisode();
  await page.goto(`/episodes/${ep.id}`);
  const first = page.getByTestId("evidence-quote").first();
  await expect(first).toBeVisible();
  const seq = await first.getAttribute("data-seq");
  const quote = (await first.innerText()).replace(/[“”]/g, "").replace(/^\[\d+\]\s*/, "").trim();
  await first.click();
  await expect(page).toHaveURL(new RegExp(`#e-${seq}$`));
  const row = page.getByTestId(`event-${seq}`);
  await expect(row).toHaveAttribute("data-selected", "true");
  await expect(row).toBeInViewport();
  const kind = await row.getAttribute("data-kind");
  if (kind === "user_message" || kind === "agent_message") {
    const norm = (s: string) => s.toLowerCase().replace(/\s+/g, " ").trim();
    await expect(row.locator("mark")).toBeVisible();
    expect(norm(await row.locator("mark").innerText())).toContain(norm(quote.split("\n")[0]).slice(0, 12));
  }
});

test("episode viewer: diff entry links to its causing event", async ({ page, seeded }) => {
  const ep = await seeded.failedEpisode();
  await page.goto(`/episodes/${ep.id}?tab=state`);
  const entry = page.getByTestId("diff-entry").first();
  await expect(entry).toBeVisible();
  await entry.getByRole("button", { name: /Go to event/ }).click();
  const hash = new URL(page.url()).hash;
  const seq = hash.replace("#e-", "");
  const row = page.getByTestId(`event-${seq}`);
  await expect(row).toHaveAttribute("data-selected", "true");
  await expect(row).toHaveAttribute("data-kind", "tool_result");
  await expect(row).toBeInViewport();
});

test("episode viewer: deep link restores selection", async ({ page, seeded }) => {
  const ep = await seeded.failedEpisode();
  await page.goto(`/episodes/${ep.id}#e-3`);
  const row = page.getByTestId("event-3");
  await expect(row).toHaveAttribute("data-selected", "true");
  await expect(row).toBeInViewport();
});

test("episode viewer: not found", async ({ page, consoleErrors }) => {
  await page.route("**/api/gauntlet/v1/episodes/*", (r) => r.fulfill(errorEnvelope(404, "not_found", "episode not found")));
  await page.goto("/episodes/ep_missing");
  await expect(page.getByText("Episode not found")).toBeVisible();
  consoleErrors.splice(0); // the mocked 404 is logged by the browser
});
