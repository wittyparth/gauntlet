# Studies: pre-registered metrics

Run `uv run python -m studies.<name> --seed N [--smoke] --out benchmarks/results/<name>.json`, then
`uv run python -m studies.render` and `uv run python -m studies.freshness --release X.Y.Z`.
Smoke configurations use scripted brains and synthetic fixtures (no model, no network, no spend).
Live full runs are manual, use only catalog models, are capped by `GAUNTLET_LIVE_BUDGET_USD`
and need the lead's go. Negative results are committed. Intervals, not point values, are rendered.

| Study | Metrics (fixed before running) | Seed | Main caveat |
|---|---|---|---|
| dva_recall | recall per DVA agent (Wilson over flaws in scope), clean-control false positives (must be 0), miss analysis | 0 | scripted brain; catalog is ours |
| judge_agreement | accuracy, fail precision/recall, Cohen's kappa with interval, cost per verdict, escalation rate, per rubric | 0 | needs the hand-labelled set of L-R3 (`--labels`) |
| reproducibility | attack-success rate over 5 reruns with interval, variance, strict replay identical | 0 | scripted brain |
| cost_per_1000 | mean cost per episode x 1000 with bootstrap interval from exported run ledgers (`--ledger`) | 0 | depends on model and scenario mix |
| simulator_fidelity | guard rule hit rate, persona-guard rubric pass rate (`--turns`) | 0 | rubric verdicts are model outputs |
| head_to_head | per-scanner recall by flaw id (`--scanners`), pinned versions, same budget | 0 | not run unless supplied; DVA favours us |
