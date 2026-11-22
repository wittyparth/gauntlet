import { mkdirSync } from "node:fs";
import path from "node:path";

import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";

// GUARD: these specs never start runs or policy tests. The gateway fixtures come from the dev seed
// (POST /v1/dev/seed with gateway: true): a policy with proposals, a stored test, decisions, one approval.
test.beforeEach(async ({ request }) => {
  const res = await request.post("/api/gauntlet/v1/dev/seed", { data: { reset: false, gateway: true } });
  expect(res.ok()).toBeTruthy();
});

const SHOTS = path.resolve(__dirname, "../../../.demo/shots");
async function themed(page: Page, name: string, prepare?: () => Promise<void>) {
  mkdirSync(SHOTS, { recursive: true });
  for (const scheme of ["dark", "light"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.evaluate((s) => localStorage.setItem("theme", s), scheme);
    await page.reload();
    await page.waitForLoadState("networkidle");
    await prepare?.();
    await page.screenshot({ path: path.join(SHOTS, `${name}-${scheme}.png`), fullPage: true });
  }
}

test("gateway console: shows seeded data", async ({ page }) => {
  await page.goto("/gateway");
  await expect(page.getByRole("heading", { level: 1, name: "Gateway" })).toBeVisible();
  await expect(page.getByTestId("stat-decisions")).toBeVisible();
  const row = page.getByTestId("decision-row").first();
  await expect(row).toBeVisible();
  await page.getByTestId("decision-row").filter({ hasText: "no-card-email" }).first().click();
  await expect(page.getByTestId("detail-rule")).toHaveText("no-card-email");
  await themed(page, "gateway-console");
});

test("gateway console: updates live", async ({ page }) => {
  const body = (ids: string[]) => ({
    items: ids.map((id, i) => ({
      id, ts: new Date(Date.now() - i * 1000).toISOString(), session_id: "s", agent_id: null, policy_id: "pol_demo", policy_version: 1,
      mode: "enforce", kind: "tool_call", tool: `tool_${id}`, args: {}, action: "block", enforced: true, would_have: null,
      rule_id: "r", severity: "high", message: null, evidence: [], approval: null, overhead_us: 10, guard_error: null,
    })),
    next_cursor: null,
  });
  let calls = 0;
  await page.route("**/api/gauntlet/v1/gateway/decisions**", (r) => r.fulfill({ json: body(++calls < 2 ? ["a"] : ["b", "a"]) }));
  await page.goto("/gateway");
  await expect(page.getByTestId("decision-row")).toHaveCount(1);
  await expect(page.getByTestId("decision-row")).toHaveCount(2, { timeout: 15_000 });
});

test("policies: shows seeded data", async ({ page }) => {
  await page.goto("/gateway/policies");
  await expect(page.getByRole("heading", { level: 1, name: "Policies" })).toBeVisible();
  const row = page.getByTestId("policy-row").filter({ hasText: "Support policy" });
  await expect(row).toBeVisible();
  await expect(row).toContainText("shadow");
  await row.click();
  await expect(page).toHaveURL(/\/gateway\/policies\/pol_demo/);
});

test("policy editor: shows seeded data and results", async ({ page }) => {
  await page.goto("/gateway/policies/pol_demo");
  await expect(page.getByRole("heading", { level: 1, name: "Support policy" })).toBeVisible();
  await expect(page.getByTestId("rule-row")).toHaveCount(3);
  await page.getByTestId("rule-row").filter({ hasText: "refund-cap" }).getByRole("button").first().click();
  await expect(page.getByLabel("when (JSON)")).toContainText("issue_refund");
  await expect(page.getByTestId("check-node").first()).toBeVisible();
  await page.getByRole("tab", { name: "Test results" }).click();
  await expect(page.getByTestId("stat-block-rate")).toContainText("75%");
  await expect(page.getByTestId("tradeoff")).toBeVisible();
  await page.getByRole("button", { name: "Table" }).first().click();
  await expect(page.getByTestId("tradeoff-table").getByRole("row")).toHaveCount(3);
  await themed(page, "policy-test-results", async () => {
    await page.getByRole("tab", { name: "Test results" }).click();
    await expect(page.getByTestId("tradeoff")).toBeVisible();
    await page.waitForTimeout(800);
  });
});

test("policy editor: rejects an invalid check", async ({ page }) => {
  await page.goto("/gateway/policies/pol_demo");
  await page.getByTestId("rule-row").filter({ hasText: "refund-cap" }).getByRole("button").first().click();
  const when = page.getByLabel("when (JSON)");
  await when.fill('{"type": tool_called}');
  await expect(page.getByTestId("check-error")).toContainText(/JSON/);
  await expect(page.getByRole("button", { name: "Save rule" })).toBeDisabled();
});

test("policy editor: enforce asks for confirmation", async ({ page }) => {
  await page.route("**/api/gauntlet/v1/policies/pol_demo/enforce", (r) => r.fulfill({ status: 500, json: { error: { code: "x", message: "blocked in test", detail: null } } }));
  await page.goto("/gateway/policies/pol_demo");
  await page.getByRole("radio", { name: "Enforce" }).or(page.getByRole("button", { name: "Enforce" })).first().click();
  await expect(page.getByTestId("mode-confirm")).toBeVisible();
  await expect(page.getByTestId("confirm-numbers")).toContainText(/block rate 75%|not been tested/);
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByTestId("mode-confirm")).toBeHidden();
});

test("approvals: approve and deny", async ({ page }) => {
  const decided: string[] = [];
  const approval = (id: string) => ({
    id, status: "pending", requested_at: new Date().toISOString(), expires_at: new Date(Date.now() + 3600_000).toISOString(),
    decided_by: null, decided_at: null, note: null,
    decision: { id: `d_${id}`, ts: new Date().toISOString(), session_id: "s", agent_id: "agt_demo", policy_id: "pol_demo", policy_version: 1, mode: "enforce", kind: "tool_call", tool: "issue_refund", args: { amount_cents: 48000 }, action: "require_approval", enforced: true, would_have: null, rule_id: "refund-cap", severity: "high", message: "held", evidence: [], approval: null, overhead_us: 1, guard_error: null },
  });
  let pending = [approval("a1"), approval("a2")];
  await page.route("**/api/gauntlet/v1/gateway/approvals?**", (r) => r.fulfill({ json: pending }));
  await page.route("**/api/gauntlet/v1/gateway/approvals/*/decide", async (r) => {
    const id = r.request().url().split("/").slice(-2)[0] ?? "";
    decided.push(`${id}:${(r.request().postDataJSON() as { decision: string }).decision}`);
    pending = pending.filter((a) => a.id !== id);
    await r.fulfill({ json: { ...approval(id), status: "approved" } });
  });
  await page.goto("/gateway/approvals");
  await expect(page.getByTestId("approval-card")).toHaveCount(2);
  await page.getByTestId("approval-card").first().getByRole("button", { name: "Approve" }).click();
  await expect(page.getByTestId("approval-card")).toHaveCount(1);
  await page.getByTestId("approval-card").first().getByRole("button", { name: "Deny", exact: true }).click();
  await page.getByRole("button", { name: "Deny this action" }).click();
  await expect(page.getByTestId("empty-state")).toContainText("Nothing waiting");
  expect(decided).toEqual(["a1:approve", "a2:deny"]);
});
