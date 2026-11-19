import { expect, test } from "./fixtures";

test("models: change a role, save, reload, value persists", async ({ page, shot }) => {
  await page.goto("/settings/models");
  await expect(page.getByRole("heading", { level: 1, name: "Models" })).toBeVisible();
  await page.getByRole("button", { name: "Reset to defaults" }).click();
  const judge = page.getByTestId("model-select-judge_strong");
  await expect(judge).toContainText("Gemini 2.5 Flash Lite");
  await shot(page, "models-defaults");

  await judge.click();
  await expect(page.getByRole("option", { name: /Qwen3\.8 Flash/ })).toContainText("Recommended");
  await page.waitForTimeout(500); // let the popup finish its entrance animation
  await shot(page, "models-select-open");
  await page.getByRole("option", { name: /Qwen3\.8 Flash/ }).click();
  await expect(judge).toContainText("Qwen3.8 Flash");

  await page.getByRole("switch", { name: "Judge (second opinion) reasoning" }).click();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Models saved")).toBeVisible();

  await page.reload();
  await expect(page.getByTestId("model-select-judge_strong")).toContainText("Qwen3.8 Flash");
  await expect(page.getByTestId("role-judge_strong")).toContainText("Set for this workspace");
  await expect(page.getByTestId("model-select-simulator")).toContainText("Qwen3.7 Flash");

  await page.getByRole("button", { name: "About Qwen3.8 Flash" }).hover();
  await expect(page.getByTestId("model-details")).toContainText("1M context".replace("1M", "1,000k"));
  await page.waitForTimeout(500);
  await shot(page, "models-saved-hover");

  await page.getByRole("button", { name: "Reset to defaults" }).click();
  await expect(page.getByText("Models reset to defaults")).toBeVisible();
  await expect(page.getByTestId("model-select-judge_strong")).toContainText("Gemini 2.5 Flash Lite");
});

test("run report header shows the resolved models", async ({ page, seeded, shot }) => {
  const run = await seeded.run();
  await page.goto(`/runs/${run.id}/report`);
  await expect(page.getByTestId("run-models")).toContainText("judge small");
  await expect(page.getByTestId("loading-rows")).toHaveCount(0, { timeout: 10_000 });
  await page.waitForTimeout(500);
  await shot(page, "run-report-models");
});

test("onboarding: hosted agent model is picked from the catalog", async ({ page, shot }) => {
  await page.goto("/onboarding");
  await page.getByLabel("Name").fill("Picker agent");
  await page.getByLabel("Purpose").fill("Answers shop order questions");
  await page.getByLabel("Policies").fill("Only refund within 30 days.");
  await page.getByRole("button", { name: "Continue" }).click();
  const picker = page.getByRole("combobox", { name: "Agent model" });
  await expect(picker).toContainText("DeepSeek V4 Flash");
  await picker.click();
  await page.getByRole("option", { name: /Mistral Small 4/ }).click();
  await expect(picker).toContainText("Mistral Small 4");
  await page.waitForTimeout(300);
  await shot(page, "onboarding-model-picker");
});
