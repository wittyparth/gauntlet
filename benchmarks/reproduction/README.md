# Benchmark reproduction

Makes Gauntlet's numbers comparable with published ones by running imported benchmark packs
(tau-bench retail, AgentDojo banking and slack) and reporting the gap honestly. Nothing here is
authored by us: the tasks and data come from the upstream repositories (licences in
`../NOTICES.md`), pinned to the commits recorded in `tools/import_benchmarks`.

## Steps

1. Clone the upstream repository at the pinned commit (a network download, done by you).
2. Import: the `importer` command of the suite in `config.yaml`. It refuses a `--pin` that is not
   the recorded one (`--allow-unpinned` overrides and prints a warning). It prints the portable
   percentage and writes `skipped.yaml` with a reason per skipped task.
3. Smoke from a committed transcript (no spend, no network), as CI does:
   `uv run python -m benchmarks.reproduction run --suite taubench_retail --model <catalog id> --smoke --trials 2 --pack <pack> --cassette-dir <dir>`
4. A live run is manual and needs the lead's go: set `GAUNTLET_LIVE_BUDGET_USD` (a hard cap; the
   harness refuses without it), then
   `uv run python -m benchmarks.reproduction run --suite taubench_retail --model <catalog id> --trials 4`.
   Only catalog models are accepted.
5. `uv run python -m benchmarks.reproduction report` renders the comparison table.

The result file `results/<suite>-<model>.json` has pass^k per k with intervals, per-task
outcomes, the pack's import metadata and the list of deviations from the published setup (user
simulator model, agent prompt, tool formatting, scoring by state-field checks instead of database
hash equality, judge off, turn limits, task coverage).

## How to read the comparison

A published number is a pass or fail only for a comparable pair (the same model); the acceptance
is within 10 points absolute on baseline utility, with a written explanation when outside. The
published numbers of these benchmarks come from OpenAI and Anthropic models that this project
does not run, so the table then shows them as context only. `config.yaml` records no published
numbers until they are read from the source and verified.
