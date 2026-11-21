# Gauntlet GitHub Action

Runs a Gauntlet suite against an agent version on a Gauntlet server, evaluates your gates, writes
the result to the job summary, keeps one comment up to date on the pull request and fails the job
when a gate fails.

## Usage

```yaml
name: gauntlet
on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read
  pull-requests: write      # the comment
  security-events: write    # only with sarif: true

jobs:
  gauntlet:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: ./integrations/github-action   # or <owner>/<repo>/integrations/github-action@<ref>
        with:
          api-url: https://gauntlet.example.com/api
          api-key: ${{ secrets.GAUNTLET_API_KEY }}
          suite: suite_support_smoke
          agent-version: agv_01HXYZ
          repetitions: 3
          budget-usd: 2
          baseline: auto
          baseline-label: main
```

The agent version is created beforehand (for example by your deploy step through
`POST /v1/agents/{id}/versions`); the action evaluates one version, it does not publish one.

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `api-url` | required | API base url, with its `/api` suffix when behind the web app proxy |
| `api-key` | required | API key from a secret |
| `suite` | required | suite id |
| `agent-version` | required | agent version id |
| `repetitions` | `1` | repetitions per scenario |
| `budget-usd` | `2` | spend cap |
| `baseline` | empty | a run id, `auto`, or empty for no comparison |
| `baseline-label` | `main` | version label `auto` looks for |
| `gates-file` | `gauntlet-gates.yaml` | gates, defaults apply if the file is absent |
| `comment` | `true` | upsert the pull request comment |
| `sarif` | `false` | export findings to code scanning |
| `cli-version` | `0.1.0` | pinned `gauntlet-cli` version |
| `timeout-min` | `30` | wait limit; the run keeps going on the server after it |
| `web-url` | empty | web app url when it is not the API host |

`baseline: auto` picks the most recent completed run of the same suite whose agent version label
equals `baseline-label`. The server has no label filter, so the CLI reads the 50 newest completed
runs of the suite and filters them itself.

Outputs: `run-id`, `gate-status` (`pass`, `fail`, `error`).

## Gates file

```yaml
gates:
  pass_rate:   {min: 0.8}
  regression:  {fail_on: [regression], warn_on: [inconclusive]}
  security:    {max_new_findings: {critical: 0, high: null}}
  reliability: {pass_hat_k: {k: 3, min: 0.6}}
  cost:        {max_usd_per_episode: 0.05, max_increase_pct: 25}
  latency:     {max_p95_ms: 8000}
  rubrics:     {min_score: 0.9, only_calibrated: true}
inconclusive: warn   # fail | warn | pass
```

Every key is optional. A gate whose input is missing (no baseline, no calibrated rubric) is
reported as `skip`, never as a failure. Rubric dimensions that have not been calibrated against
human labels never fail the job. Unknown keys are an error, so typos do not silently disable a gate.

The step exits like `gauntlet gate`: 0 passed (warnings allowed), 1 a gate failed, 3 platform error
(the run did not finish, nothing was counted, the server was unreachable).

## Pull requests from forks

GitHub does not hand secrets to workflows triggered by fork pull requests. The action then prints
a notice and skips the comment; the run itself cannot start without the key either. Use
`pull_request_target` only if you understand the implications of running with secrets next to
untrusted code, and never check out the fork's head in that job.

## Secrets handling

The API key reaches the CLI through the `GAUNTLET_API_KEY` environment variable of the step only.
It is never placed in a command line, a `run:` expression or an output.

## Tests

```sh
node --test "integrations/github-action/scripts/*.test.js"
uv run pytest tests/integrations
```

## Trying it end to end

1. Start the compose stack and expose the API, for example `cloudflared tunnel --url http://localhost:8000`.
2. Create a throwaway repository with the workflow above and the tunnel url as `api-url`.
3. Open a pull request: one `<!-- gauntlet-report -->` comment appears. Push again: the same comment
   is edited. Lower a gate threshold below the run's results to see the job fail.
