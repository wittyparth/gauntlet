import { describe, expect, it } from "vitest";

import type { ModelSettings, RoleChoice } from "@/lib/api/models";

import { priceLabel, rolesToSave, shortModel } from "./draft";

const initial: ModelSettings = {
  roles: {
    simulator: { model: "openrouter/qwen/qwen3.7-flash", reasoning: "off" },
    judge_strong: { model: "openrouter/google/gemini-2.5-flash-lite", reasoning: "off" },
  },
  overridden: ["simulator"],
};

describe("rolesToSave", () => {
  it("keeps existing overrides and adds changed roles only", () => {
    const draft: Record<string, RoleChoice> = {
      simulator: { ...initial.roles.simulator },
      judge_strong: { model: "openrouter/qwen/qwen3.8-flash", reasoning: "low" },
    };
    expect(Object.keys(rolesToSave(initial, draft)).sort()).toEqual(["judge_strong", "simulator"]);
  });
  it("sends nothing when nothing is overridden or changed", () => {
    const draft: Record<string, RoleChoice> = { ...initial.roles };
    expect(rolesToSave({ ...initial, overridden: [] }, draft)).toEqual({});
  });
});

describe("labels", () => {
  it("formats the price per million tokens", () => {
    expect(priceLabel({ input_usd_per_mtok: 0.03, output_usd_per_mtok: 0.13 })).toBe("$0.03 / $0.13 per 1M");
  });
  it("keeps a third decimal when the price needs it", () => {
    expect(priceLabel({ input_usd_per_mtok: 0.075, output_usd_per_mtok: 0.4 })).toBe("$0.075 / $0.40 per 1M");
  });
  it("shortens a model id", () => {
    expect(shortModel("openrouter/qwen/qwen3.7-flash")).toBe("qwen3.7-flash");
  });
});
