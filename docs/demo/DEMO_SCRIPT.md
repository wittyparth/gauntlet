# Gauntlet live demo script

Story: "We test an AI support agent the way an attacker and a QA team would, find a real hole, turn it into a policy rule, prove the rule works offline, enforce it, and show the evidence."

Runtime about 12 minutes. Steps 1 to 4 and the policy pages of step 8 use only data created by the seed (scripted model, no spend), so they work with no provider key. Steps 5 to 7 start live runs against the Damn Vulnerable Agent (DVA) and spend model credits, capped by `GAUNTLET_MAX_RUN_BUDGET_USD_MICROS` and `GAUNTLET_DAILY_BUDGET_USD`. Page names are the left-nav labels. Expected values for the seeded data are exact; expected values for live steps are what the rehearsal should show, so confirm them once before presenting.

## Before the audience arrives

1. Deploy (`deploy/README.md`), then check the stack: `GAUNTLET_API_KEY=gk_... BASE_URL=https://your.host scripts/demo_smoke.sh` ends with `0 failed`.
2. Seed is already loaded by `bootstrap.sh`. To rebuild it: `docker compose -p gauntlet -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod exec api python -m gauntlet_server.demo seed --reset`.
3. For the live steps: `OPENROUTER_API_KEY` set in `deploy/.env.prod`, a spend limit set on the key at openrouter.ai, and the stack restarted. Leave the kill switch (Security page) disengaged.
4. Open the console, paste the admin API key on the login page.

## 1. An eval run with failures: Runs

- Page: **Runs**, click `run_demo` (suite `ecommerce_smoke`, agent "Demo support agent").
- Expected: status done, 10 episodes, 9 passed and 1 failed. The live panel shows the finished state.
- Say: "This is a regression suite for a refunds agent, judged by rubric checks, not vibes."
- Click **Report** (`/runs/run_demo/report`): per-scenario table and a failure card for `scn_ecom_07`, a refund outside the return window.

## 2. Episode view: the failing episode

- From the report failure card, open the failed episode (`ep_demo_6`).
- Expected: transcript with the tool timeline; the `issue_refund` call; a state diff (the world patch showing the refund applied); a failing verdict whose evidence quote is highlighted in the cited event.
- Say: "Every verdict cites the exact event. Click the quote and the transcript scrolls to it."

## 3. Replay and compare: Runs, compare view

- Page: **Runs** then `run_demo` then **Compare with a baseline run**, choose `run_demo_b` as the baseline (`/runs/run_demo/compare`).
- Expected: summary showing no detectable change (both runs are the same scripted suite), a flip table with no newly failing or newly passing scenarios, and **Compare trajectories** available per scenario.
- Say: "Same suite, same seed, so a change in results is the agent's change, not noise. Replays are deterministic where the cassette allows."
- Optional live: on the failing episode choose **Replay** to start a replay (spends a little if it re-calls the model).

## 4. The agent's scorecard: Agents

- Page: **Agents**, "Demo support agent", **Scorecard** (`/agents/agt_demo/scorecard`).
- Expected: posture and coverage sections for the version; benign pass rate from the seeded runs; attack coverage empty or low until step 5 runs.

## 5. Security campaign on the DVA: Security (live)

- Page: **Security**, **New campaign** (`/security/campaigns/new`).
- Fill in: **Agent version** "Damn Vulnerable Agent (wired), dva-wired"; **Benign suite** `ecommerce_smoke`; **Max attacks** 10 to 20; **Repetitions** 1; categories as offered.
- The target `http://dva:8100` is on the allowed local-host list, so no ownership verification is needed. A real external target needs a verified DNS or HTTP challenge first (Security page, ownership card).
- Start the campaign. Expected: "Campaign started", run progress streams in, attack episodes appear grouped by category, and some objectives hold (the attack succeeded) because the DVA has 19 planted flaws.
- Say: "The DVA is deliberately broken. This is what finding real holes looks like."

## 6. A finding: Findings (live, follows step 5)

- Page: **Findings**. Expected: clustered findings with severity, for example a refund or data-exfiltration flaw, each with evidence episodes and a **Reproduce** card.
- Open the top finding: header with status, evidence episodes, the reproducer, and the **Suggested policy rule** card.

## 7. Suggested rule, offline test, enforce, verify (live for the verify step)

1. On the finding, the **Suggested policy rule** card shows a rule (for example require approval for `issue_refund` above a threshold). Click **Add to policy**, choose the demo policy `pol_demo`.
2. Page: **Gateway** then **Policies** then `pol_demo`. Expected: the rule list with the new rule; run the policy test (no model calls: it replays recorded trajectories through the rule engine). Expected: a result with a block rate above the 50 percent gate and a false-positive rate at or under the 2 percent gate on benign trajectories, and the tradeoff chart.
3. Set the gateway **Mode** control from **Shadow** (observe, log what would be blocked) to **Enforce**. Expected: the enforce gate passes only if the offline test met both gates; otherwise it explains which gate failed.
4. Back on the finding choose **Verify the fix**. Expected: "Verification started", the same attacks re-run through the enforced policy, and the finding moves to verified when they no longer succeed.
- Say: "Find, propose, test offline, enforce, verify. A rule never ships on a hunch."

The seeded `pol_demo` already has a published version, proposals, a finished policy test, a few gateway decisions and one pending approval, so this part of the story works without step 5. See **Gateway** then **Approvals** for the pending refund.

## 8. Scorecard and badge: Agents

- Page: **Agents**, the DVA agent, **Scorecard**. Expected: attack coverage by category, benign vs attack trajectories, the fix verification. Create the badge from the scorecard; it renders as a public SVG at `/v1/badges/...` that you can embed in a README.
- Say: "That badge is evidence-backed and expires, so it cannot drift from reality."

## Fallbacks

- No provider key or spend exhausted (`HTTP 429 daily_budget_exceeded`): run only steps 1 to 4 and the seeded policy part of step 7. Raise `GAUNTLET_DAILY_BUDGET_USD` and restart to continue.
- Something is running away: Security page, kill switch card, engage it; or set `GAUNTLET_ATTACKS_DISABLED=true`.
- Reset the demo rows: the `--reset` command above.
