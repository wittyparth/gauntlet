import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LabelBar } from "./label-bar";

function setup(disabled = false) {
  const h = { onLabel: vi.fn(), onSkip: vi.fn(), onNext: vi.fn(), onPrev: vi.fn(), onToggleJudge: vi.fn() };
  render(<LabelBar disabled={disabled} announcement="" {...h} />);
  return h;
}

describe("LabelBar hotkeys", () => {
  it("maps p, f, n to labels and s, j, k, h to navigation", async () => {
    const h = setup();
    const u = userEvent.setup();
    await u.keyboard("pfnsjkh");
    expect(h.onLabel.mock.calls.map((c) => c[0])).toEqual(["pass", "fail", "na"]);
    expect(h.onSkip).toHaveBeenCalledTimes(1);
    expect(h.onNext).toHaveBeenCalledTimes(1);
    expect(h.onPrev).toHaveBeenCalledTimes(1);
    expect(h.onToggleJudge).toHaveBeenCalledTimes(1);
  });

  it("does not label while disabled", async () => {
    const h = setup(true);
    await userEvent.setup().keyboard("fpn");
    expect(h.onLabel).not.toHaveBeenCalled();
  });
});
