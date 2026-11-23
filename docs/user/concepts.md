# Concepts

**Pack.** A directory of scenarios, a mock world, a policy and suites (`pack.yaml`, `world.yaml`, `policy.md`, `scenarios/`, `suites/`). Everything the agent touches is in the world: tools are handlers over fake data, so nothing real can be harmed.

**Episode.** One conversation between a simulated user and the agent in a world, ended by a goal, a give-up, a turn limit or a budget. The outcome is a trajectory: messages, tool calls, results and world changes.

**Journal.** The append-only record of an episode, exported as a *cassette* (`*.cassette.jsonl`). Every effect (model output, tool result, human input) is journaled, so `gauntlet replay` reproduces an episode without calling anything, and `gauntlet rejudge` re-evaluates it with new checks or judges.

**Check language.** Deterministic assertions over a trajectory: which tools were called with which arguments, what the world looks like afterwards, what text appeared. Checks are data (YAML or JSON), validated by a JSON Schema: see the [reference](reference/check-language.md). Checks decide `violates`, `ok` or `undetermined`; they never guess.

**Rubrics and judges.** Where a check cannot decide (tone, task completion) a rubric is scored by a judge model cascade. Uncalibrated rubrics are reported but cannot gate CI.

**Findings.** Failing episodes are clustered into findings with a severity, evidence (episode and step references) and a lifecycle. A finding can be replayed, verified after a fix, pinned as a regression test, or exported.

**Policies.** Runtime rules (allow, deny, require approval, taint) compiled from policy text, checked with `gauntlet policy`, and enforced by the gateway. Compiling proposes rules; a person publishes them.

**Statistics.** Pass rates come with intervals, and reliability is reported as pass^k over repetitions. Negative results are kept: see [benchmarks](../benchmarks/index.md).
