import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Verdict } from "@/lib/api/models";

import { sortVerdicts, VerdictList } from "./verdict-list";

const v = (criterion: string, result: Verdict["result"], severity: Verdict["severity"], hard_fail = false): Verdict => ({
  criterion,
  evaluator: `rule:${criterion}`,
  result,
  severity,
  hard_fail,
  stage: "rule",
  model: null,
  confidence: 1,
  reasoning: "",
  evidence: [],
  cost: null,
});

describe("sortVerdicts", () => {
  it("orders hard fails, fails by severity, errors, passes, then n/a", () => {
    const sorted = sortVerdicts([
      v("a_pass", "pass", "high"),
      v("b_na", "na", "low"),
      v("c_fail_medium", "fail", "medium"),
      v("d_error", "error", "high"),
      v("e_fail_critical", "fail", "critical"),
      v("f_hard", "fail", "low", true),
    ]);
    expect(sorted.map((x) => x.criterion)).toEqual([
      "f_hard",
      "e_fail_critical",
      "c_fail_medium",
      "d_error",
      "a_pass",
      "b_na",
    ]);
  });
});

describe("VerdictList", () => {
  const noop = () => {};
  it("tells a finished episode with no verdicts that no evaluators ran", () => {
    render(<VerdictList verdicts={[]} done activeEvidence={{ seq: null, quote: null }} onSelectEvidence={noop} />);
    expect(screen.getByText("No evaluators ran")).toBeInTheDocument();
  });
  it("tells a running episode that verdicts are not in yet", () => {
    render(
      <VerdictList verdicts={[]} done={false} activeEvidence={{ seq: null, quote: null }} onSelectEvidence={noop} />,
    );
    expect(screen.getByText("No verdicts yet")).toBeInTheDocument();
  });
  it("renders one card per verdict with its criterion", () => {
    render(
      <VerdictList
        verdicts={[v("task_completion", "fail", "high"), v("tone", "pass", "low")]}
        done
        activeEvidence={{ seq: null, quote: null }}
        onSelectEvidence={noop}
      />,
    );
    expect(screen.getAllByTestId("verdict-card")).toHaveLength(2);
    expect(screen.getByText("task_completion")).toBeInTheDocument();
  });
});
