import { describe, expect, it } from "vitest";

import {
  agentStepSchema,
  budgetMicros,
  runStepSchema,
  targetStepSchema,
  toVersionBody,
  type AgentStep,
} from "./wizard-schema";

const agent: AgentStep = {
  name: "Support",
  purpose: "Shop support",
  audience: "",
  policies_text: "Be nice.",
  forbidden_behaviors: "never refund twice\n\nnever share emails",
  languages: "en, es",
};

describe("wizard schemas", () => {
  it("requires a name and a purpose", () => {
    const r = agentStepSchema.safeParse({ name: " ", purpose: "" });
    expect(r.success).toBe(false);
    if (!r.success) expect(r.error.issues.map((i) => i.path[0])).toEqual(["name", "purpose"]);
  });

  it("requires hosted model, prompt and world", () => {
    const r = targetStepSchema.safeParse({ kind: "hosted", model: "", system_prompt: "", temperature: 0, world_id: "", tools: null });
    expect(r.success).toBe(false);
  });

  it("validates remote URLs", () => {
    expect(
      targetStepSchema.safeParse({ kind: "openai_compat", base_url: "not a url", model: "m" }).success,
    ).toBe(false);
    expect(
      targetStepSchema.safeParse({ kind: "openai_compat", base_url: "https://host.test/v1", model: "m" }).success,
    ).toBe(true);
  });

  it("requires body_template to parse as a JSON object", () => {
    const base = { kind: "http", url: "https://a.test/chat", reply_path: "reply" } as const;
    expect(targetStepSchema.safeParse({ ...base, body_template: "{oops" }).success).toBe(false);
    expect(targetStepSchema.safeParse({ ...base, body_template: "[1]" }).success).toBe(false);
    expect(targetStepSchema.safeParse({ ...base, body_template: '{"message":"{{user_message}}"}' }).success).toBe(true);
  });

  it("converts dollars to integer micro-dollars", () => {
    expect(budgetMicros(2)).toBe(2_000_000);
    expect(Number.isInteger(budgetMicros(0.1 + 0.2))).toBe(true);
    expect(runStepSchema.safeParse({ suite_id: "s", repetitions: 1.5, budget_dollars: 2 }).success).toBe(false);
    expect(runStepSchema.safeParse({ suite_id: "s", repetitions: 1, budget_dollars: 0 }).success).toBe(false);
    expect(runStepSchema.safeParse({ suite_id: "s", repetitions: 1, budget_dollars: 2 }).success).toBe(true);
  });

  it("builds the version body for each target kind", () => {
    const hosted = targetStepSchema.parse({
      kind: "hosted",
      model: "openrouter/x",
      system_prompt: "You help.",
      temperature: 0,
      world_id: "ecommerce",
      tools: null,
    });
    const body = toVersionBody(agent, hosted);
    expect(body.world_id).toBe("ecommerce");
    expect(body.profile.forbidden_behaviors).toEqual(["never refund twice", "never share emails"]);
    expect(body.profile.languages).toEqual(["en", "es"]);
    expect(body.target).toMatchObject({ kind: "hosted", model: "openrouter/x" });

    const http = targetStepSchema.parse({
      kind: "http",
      url: "https://a.test/chat",
      reply_path: "reply",
      body_template: '{"m":"x"}',
      headers: "X-Key: abc\nbad line",
    });
    const hb = toVersionBody(agent, http);
    expect(hb.target).toMatchObject({ kind: "http", headers: { "X-Key": "abc" }, body_template: { m: "x" } });
  });
});
