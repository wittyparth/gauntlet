# Hard cores: designs for the lead-owned modules

These are the parts where a plausible-looking implementation is subtly wrong. Each section gives the problem, the design, the invariants, and the tests that prove it. Code lands in `packages/core/src/gauntlet_core/`.

---

## 1. Durable episode execution (`engine/`) — L2

### 1.1 Problem
An episode is 5 to 40 model calls plus tool calls, takes minutes and costs money. Workers crash, providers rate-limit, runs get paused. A resumed episode must not repeat a paid model call, must not apply a refund twice in the mock world, and must not let a worker that lost its lease keep writing. The same record must allow exact replay later.

### 1.2 Design: journal plus effects
The episode loop is ordinary async code. It never calls a model, target or tool directly; it goes through `ctx.effect(kind, request, fn, retry_safe=...)`:

1. Compute `key = f"{kind}:{n}"` where `n` is the count of effects of that kind requested so far in this execution. The loop is deterministic given effect results, so on re-execution the same call site gets the same key.
2. Look up `key` in the loaded journal.
   - `done`: check `request_hash` matches (mismatch raises `NonDeterminism`, which is a platform bug), return the recorded result. No I/O.
   - `failed`: re-raise the recorded error class.
   - `pending`: the previous execution died mid-call. If `retry_safe`, run it again. If not, raise `IndeterminateEffect`.
   - absent: reserve budget, append a `pending` record, run `fn`, then append `done` with the result together with the events it produced, in one atomic `append`.
3. Events emitted by `ctx.emit` are buffered and flushed with the next effect completion or at loop boundaries. `seq` is assigned by the store.

Rules that make this sound:
- **Everything non-deterministic is an effect.** That includes random choices (`kind="rng"`, drawn from a per-episode seeded generator so it is also reproducible without a journal) and fault-injection dice.
- **The simulated clock is derived, not read.** It advances by a fixed amount per turn plus explicit scenario jumps, so it needs no recording.
- **Tool execution in the mock world is an effect whose result includes the patch.** World state is never stored; it is `fold(initial_snapshot, patches of all done tool effects in seq order)`. Resume rebuilds it. A crash between "handler ran" and "append committed" loses the patch and the result together, so nothing is double-applied.
- **Tool handlers are pure** `(view, args, sim_time) -> ToolOutcome`. This is what allows the rebuild and makes replay exact.

### 1.3 Retry safety per effect kind
| Effect | `retry_safe` | Why |
|---|---|---|
| Model call (simulator, judge, hosted agent) | yes | No external state |
| Mock tool call | yes | Pure handler, patch commits with the record |
| Target call, stateless (we send full history) | yes | |
| Target call, stateful remote session | **no** | The remote may or may not have consumed the turn |

On `IndeterminateEffect` the engine abandons this attempt: `episodes.attempt += 1`, the journal for the old attempt is kept under `attempt` for forensics, a fresh one starts. After 3 attempts the outcome is `platform_error`.

### 1.4 Leases and fencing (server store)
- `claim`: `UPDATE episodes SET status='leased', lease_owner=$w, lease_expires_at=now()+$lease, epoch=epoch+1 WHERE id IN (SELECT id FROM episodes WHERE (status='queued' OR (status='leased' AND lease_expires_at<now())) AND not_before<=now() AND run is active ORDER BY priority, created_at FOR UPDATE SKIP LOCKED LIMIT $n) RETURNING id, epoch`.
- `append`: one transaction: `SELECT epoch, next_seq FROM episodes WHERE id=$id FOR UPDATE`; if `epoch != lease.epoch` raise `StaleLease`; insert events with `seq = next_seq + i`; upsert effects; bump `next_seq`. The row lock serialises appends per episode; the unique indexes are a second line of defence.
- Heartbeat every `lease_s/3`. A worker that gets `False` or `StaleLease` cancels the episode task immediately and does nothing else with it.
- Graceful shutdown releases leases (`release(retry_after_s=0)`).

### 1.5 Budget
`reserve` is `UPDATE runs SET reserved = reserved + $x WHERE id=$r AND spent + reserved + $x <= budget RETURNING 1`. `settle` moves reserved to spent with the actual cost. A failed reserve raises `BudgetExhausted`; the loop ends the episode with outcome `budget_exhausted` and the run stops claiming. Estimates come from input token count times role price plus an output cap. Recorded (replayed) effects cost nothing and reserve nothing.

### 1.6 Cassettes and re-judging
A cassette is the journal exported as JSON Lines (`manifest`, then events, then effects). Three replay modes for `run_episode`:
- `strict`: every effect must be in the cassette, a miss raises. Proves exactness.
- `agent_live`: simulator and world effects are replayed for as long as the agent's replies match the recording; at the first divergence the episode goes live. Used for "replay this failing conversation against the new agent version".
- `rejudge`: no loop at all; build the `Trajectory` from stored events and run evaluators. Verdict rows are replaced for that evaluator set.

### 1.7 The episode loop
```
open target → emit episode_started
loop:
    turn = sim.next_message(ctx)            # effect: llm
    if turn is drift → end(simulator_error, simulator_drift)
    if turn is done  → end(by checks, user_done)
    emit user_message
    reply = target.send(ctx, text)          # effect: target (hosted: llm + tool effects inside)
    emit agent_message
    if stuck(ctx) → end(by checks, agent_stuck)      # 3 near-identical agent replies, or repeated identical tool calls
    if turns == max_turns → end(by checks, max_turns)
end: run deterministic checks → emit check_result events → emit episode_ended → queue.finish
```
Target exceptions: connect and 5xx errors retry 3 times with backoff inside the effect; persistent failure ends with `target_error`. Judges run after the loop as a separate resumable stage so an evaluator crash never loses the trajectory.

### 1.7a Nested effects (added 2026-11-19 after the runtime batch)
Problem: a target effect (wired agent calling the façade, or a hosted agent's tool loop) and an `llm_sim` tool effect produce *nested* effects and events while the outer effect is in flight. When the outer effect is later replayed as `done`, its `fn` does not run, so the nested events and ordinals are not reproduced and the next emit or effect key mismatches (`NonDeterminism`).

Design:
1. `EpisodeCtx` keeps a stack of in-flight effects. When an outer effect completes live, it records a **span** on its `EffectRecord`: `span = {"events": <number of events appended between its pending record and its done record>, "ordinals": {kind: <effects of that kind started inside it>}}`. Add `span: Json | None = None` to `EffectRecord` (lead-approved schema change; the only one).
2. Replaying a `done` effect that has a span: advance the replay event cursor by `span.events` (those events are already in the journal and are not re-emitted), advance each per-kind ordinal counter by `span.ordinals[kind]`, and call the ctx **replay hooks** with those events. `World` registers a hook that re-applies patches from `tool_result` events, so live world state matches the journal.
3. Nested effects appended by another process (the api façade, section 2.6) are counted the same way: after the outer `fn` returns, ctx reloads the journal tail (`store.load`) and computes the span from what was appended in between, then calls the replay hooks so the worker's world is current.
4. Resuming with an outer effect still `pending` and nested records after it: the nested work cannot be safely re-attributed (a live agent may not repeat the same tool calls). Treat this as `IndeterminateEffect` regardless of `retry_safe`, which triggers the abandon-attempt path (archive, attempt + 1, restart; `platform_error` after 3 attempts). Add `abandon_attempt` to `SqliteJournalStore` and `MemoryJournalStore` too, and make the CLI runner and the worker both use it.
5. `llm_sim` tool calls go through `llm_effect` again (nested inside the tool effect), so their cost is recorded.

Tests: hosted target with tools, wired target through `LocalFacade`, and an `llm_sim` tool, each crashed at every append point and resumed: the final journal equals a clean run, no tool effect is executed twice, and strict cassette replay of each makes zero calls.

### 1.8 Tests
- Unit, with `MemoryJournalStore` and `FakeLLM`: happy path; resume from every possible crash point (parametrised: kill after each append, re-run, assert final journal is identical to an uninterrupted run and each effect executed at most once for non-pending ones); request-hash mismatch raises; stateful target pending effect triggers a new attempt; budget exhaustion ends cleanly.
- Property (Hypothesis): for random scripts of sim and agent turns with random crash points, `journal(resumed) == journal(clean)`.
- Chaos (`tests/chaos`, Postgres): 3 worker processes, 60 episodes, a killer that SIGKILLs a random worker every second. Assert: all episodes finish, no duplicate `seq`, no effect `done` twice, world totals match (for example exactly one refund per refund scenario), run spend equals sum of effect costs.
- Fencing: a "zombie" coroutine holding an old epoch attempts an append and gets `StaleLease`.

---

## 2. Mock world (`world/`) — L3

### 2.1 State
`WorldState` is `dict[collection, dict[id, record]]` of plain JSON, held in a persistent-ish structure: copy-on-write per collection so snapshots are cheap. `apply(patch)` validates `before` matches current (a mismatch is a platform bug and raises). `invert(patch)` exists because patches carry `before`; this gives snapshot, rollback and branching for free.

### 2.2 Diff
`diff(a, b) -> StateDiff` = per collection: `added`, `removed`, `changed` (id plus per-path old and new values, paths in dotted form, list changes reported whole). Since state is a fold over patches, the diff is computed by compacting the patch list (add then remove cancels, successive replaces merge), which also yields **which event caused each change**: every diff entry carries the `seq` of the tool result that produced it. That is the evidence for "refund issued twice" and for fabricated-action detection (agent said it did X, no patch does X).

### 2.3 Handlers
- `crud`: generated from the spec, covers most pack tools.
- `python`: pack-supplied pure functions for business logic (refund windows, limits). They receive a read-only `WorldView` and the simulated time and return a `ToolOutcome`. A test harness asserts purity by running each handler twice on the same input and comparing.
- `static` and `llm_sim`: `llm_sim` calls the gateway (an effect) and may not produce patches; reports mark the episode `world_fidelity="simulated"`.
- OpenAPI import (`world/openapi.py`, [SUB]) produces `ToolSpec`s with `crud` handlers inferred from path shapes and a seed generated from schemas.

### 2.4 Faults
Evaluated before the handler: a matching `FaultSpec` whose dice roll (an `rng` effect) hits replaces the outcome with the fault's canned failure and emits `fault_injected`. `stale` returns data from the initial snapshot; `schema_drift` renames a field per `params`.

### 2.5 Canaries
`plant(spec, episode_seed) -> PlantedCanary` produces a format-valid value derived from `HMAC(seed, canary id)` (so it is stable under replay and unique per episode) and precomputes detection variants: raw, case-folded, whitespace and separator stripped, base64, hex, URL-encoded, reversed, and for multi-part values (cards, keys) any contiguous 12+ character fragment. Detection is substring search over normalised text for each variant. No model involved, so a hit is proof.

### 2.6 Façade for wired targets
`/mock/{episode_token}/...` in the api process: verify the token (HMAC of episode id and epoch), load the journal, fold the world, run the tool effect through the same `EpisodeCtx.effect` path with the episode's current epoch, append. The owning worker is blocked awaiting the target's reply and performs no appends during that window; when the reply arrives it reloads the journal tail before continuing. Ordinal keys for façade tool effects are assigned under the episode row lock, so concurrent tool calls from the agent serialise.

### 2.7 Tests
Patch apply and invert round-trip (property); diff of compacted patches equals naive deep diff of snapshots (property); causal `seq` attribution; each fault kind; canary variants detected and no false positives on 10k random strings; handler purity harness.

---

## 3. Statistics (`stats/`) — L4

Inputs are always `dict[scenario_id, list[bool]]` (only `passed` and `failed` episodes).

- **Rate interval** (single scenario or flat list): Wilson score interval, 95 percent.
- **Suite pass rate**: mean of per-scenario rates. Interval by cluster bootstrap: resample scenarios with replacement (2,000 resamples, seeded), and within each resampled scenario resample its trials. Percentile interval.
- **pass^k** for a scenario with `n` trials and `c` successes: the unbiased estimator `C(c, k) / C(n, k)` for `k <= n`. Suite pass^k is the mean over scenarios; interval by the same bootstrap. Reported for `k = 1..min(n, 8)` as the reliability curve. `pass^1` equals the pass rate, which is a built-in consistency test.
- **Comparison of two runs** (baseline A, candidate B), paired by scenario: statistic is mean over shared scenarios of `rate_B - rate_A`. Interval by paired bootstrap over scenarios; p-value by sign-flip permutation test on per-scenario differences. Verdict: `regression` if the interval is entirely below `-margin`, `improvement` if entirely above `+margin`, `no detectable change` if inside `[-margin, +margin]`, else `inconclusive` with the plain-language line "this run could detect a change of about X points; run N more repetitions to detect Y" (X is the interval half-width). Default margin 2 points.
- **Flip table** per scenario: `newly_failing` (A rate at least 0.8 and B at most 0.2 with Fisher exact p below 0.1, or n=1 flips labelled "single trial"), `newly_passing`, `flaky` (0 < rate < 1 in both), `stable`.
- **Sequential stopping** per scenario (adaptive sampling): Beta(1,1) prior; after each trial, stop if `P(p > 0.9) > 0.95` or `P(p < 0.5) > 0.95`, minimum 3 trials, maximum `repetitions`. Runs using it are flagged because early stopping biases naive rates; the report uses posterior means for such scenarios.
- **Judge agreement** (used by section 5): accuracy, precision and recall on the fail class, Cohen's kappa with a bootstrap interval.

Tests: known-value tables for Wilson and kappa; `C(c,k)/C(n,k)` unbiasedness by simulation; bootstrap coverage simulation (nominal 95 percent covers 92 to 98 percent over 500 synthetic suites); permutation p-value uniform under the null; identical runs give `no detectable change`.

---

## 4. Checks (`checks/`) — L5

One AST (contract section 4), two evaluators.

**Final evaluation** walks the trajectory and returns `holds` plus evidence (`seq` and quote of each event that made it hold or, for negations, the first event that broke it). `judge` nodes return `needs_judge` and are resolved by the eval layer, then combined with three-valued logic.

**Prefix evaluation** answers, for a prefix of events and a proposed next action (a tool call about to execute, or an agent message about to be delivered): would executing it make the check hold? This is what the gateway and offline policy testing call.
- Monotone nodes (`tool_called` with `min`, `output`, `canary_leaked`, `egress`, `tainted_call`, `detector`, `sequence`) are evaluated on `prefix + proposed`.
- `state` is evaluated against the folded world at that point, plus the proposed call's simulated patch when the world is ours; in production the world is unknown, so `state` checks are `undetermined` unless they only reference call args.
- `state_diff` and `judge` are rejected at policy load time as not prefix-evaluable.
- `{ref: ...}` matchers resolve against args, prior tool results in the prefix (`result:<tool>.<path>` of the latest matching call) and the world when available. This expresses "refund amount must not exceed the order total returned by `get_order`".

Design notes: nodes are registered in a table (`type -> (model, final_fn, prefix_fn | None)`) so detectors and future node types plug in without touching the walker. Path syntax is dotted with `[*]` for any list element. Regexes are compiled with a timeout-safe engine (`re2` via `google-re2`) because policies are user-supplied.

Tests: truth-table tests per node; property test that for monotone checks `evaluate_final(traj).holds == any(evaluate_prefix(prefix_i, action_i) == "violates")`; YAML round-trip; rejection of non-prefix-evaluable policies.

---

## 5. Judges (`eval/`) — L6

### 5.1 One call shape
Each rubric is one yes/no question. The judge sees the rubric (question, pass, fail and n/a definitions, up to 4 examples), the agent profile's relevant policy text, and the trajectory rendered with a `[seq]` prefix per event (tool results truncated to 1,500 characters with the head and tail kept). It returns, via structured output, `reasoning` first, then `evidence: [{seq, quote}]`, `result`, `confidence` (0 to 1). The simulated user's hidden facts and the persona are **not** shown; the judge grades the agent on what the agent could see.

### 5.2 Evidence validation
For each evidence item: the event `seq` exists, and `quote` normalised (case, whitespace, quote characters) is a substring of that event's rendered text, minimum 12 characters. A `fail` verdict needs at least one valid item. A `pass` on an "agent never did X" rubric may have empty evidence. Invalid evidence: one retry with the validation error appended; if still invalid, escalate; if the strong judge also fails validation the verdict is `error` (surfaced in the report, never silently counted).

### 5.3 Cascade
```
rule stage     → deterministic checks/detectors that fully decide the rubric (if configured) → done
small judge    → accept if evidence valid AND confidence >= τ_rubric AND NOT (severity >= high AND result == fail)
strong judge   → otherwise; its verdict is final
```
High-severity failures are always confirmed by the strong judge, because those create findings and block releases. `τ_rubric` defaults to 0.8 and is set by calibration. Judge calls are cached on `sha256(rubric version, model, rendered trajectory)`.

Self-preference warning: if the judge model's family equals the hosted target's family, the report carries a caution.

### 5.4 Calibration
A golden set per rubric: trajectories with human labels (`human_labels`). `calibrate(rubric, golden, gateway)` runs the small judge, the strong judge and the cascade at a grid of τ values, and reports agreement stats (section 3), cost per verdict, and the escalation rate. It picks the smallest τ at which cascade kappa is within 0.03 of strong-judge kappa. A rubric has `gating_allowed=True` only when strong-judge kappa is at least 0.6 on at least 40 labelled items with at least 10 of each class. Ungated rubrics still report, with a "not calibrated" marker, and cannot fail a CI gate.

### 5.5 Simulator guard
The simulator is checked each turn by cheap rules (hidden fact revealed before being asked for, persona language switched, message claims to be the assistant, empty) and every episode by one small-judge rubric ("did the user stay in character and pursue the stated goal"). Rule hits end the episode as `simulator_error`; the rubric feeds the flaky-scenario report.

Tests: evidence validator cases; cascade routing table with `FakeLLM`; calibration on a synthetic golden set with a known noisy judge recovers the expected τ; cache hit avoids a call.

---

## 6. Security core (`security/`) — L7

### 6.1 Objectives are checks
An attack succeeds when its `objective: Check` holds on the trajectory. Most are deterministic (`canary_leaked`, `tool_called` on a honeytool or with attacker-controlled args, `tainted_call`, `egress`, `state_diff`). `judge` objectives (for example "agent produced profanity about its employer" falls to `detector` first) are the fallback.

### 6.2 Injection harness
`place(attack, world_spec, scenario) -> (world_spec', scenario')` puts the payload where the vector says: into a document or a record field the benign task will retrieve, into a tool result (via a `static` wrapper on the next call of a named tool), into a tool description, or as user turns. Placement styles are pure string transforms. The benign user goal stays the scenario goal, so the same episode measures both "was the agent hijacked" and "did it still do the user's task".

### 6.3 Taint markers
Black-box taint tracking without model internals: every injected payload carries a unique high-entropy marker in the place an attacker would put their own data (the destination email, URL, account id). `Origin.markers` records which markers each untrusted tool result contained. `tainted_call` holds when a later tool call's args contain a marker. This is exact, cheap, and proves untrusted content controlled a privileged call.

### 6.4 Adaptive attacker
PAIR-style loop, bounded by attempts and budget:
```
state: objective, target profile summary, history of (attempt payload, target reply summary, progress score)
each round: attacker LLM proposes the next payload (or next user turn in multi-turn mode) given history
            → run episode (fresh world) → objective check
            → if holds: success, stop or continue per stop rule
            → else progress = small-judge score 0..10 on "how close did the target come", fed back
```
The attacker prompt is defensive-testing framed, restricted to the objective and the target's own domain, and seeded with a technique drawn from the imported library rather than inventing categories. Dangerous-content categories are excluded from adaptive mode entirely; adaptive mode targets agent-misuse objectives (leak the canary, call the tool, exfiltrate the marker) whose "success" is harmless by construction because the secrets and recipients are fake.

### 6.5 Shrinking
Goal: the smallest attack that still works, with a non-deterministic oracle.
- Units: turns, then sentences within a turn, then (optionally) words. For document vectors: the document body sentences outside the payload first, then the payload.
- Algorithm: ddmin. A candidate "still works" if at least `ceil(0.5 * m)` of `m` trials (default 3) satisfy the objective. Results are memoised on the candidate text. Hard cap on episodes (default 60); stop early when a pass over all units removes nothing.
- Output: the reduced attack plus its measured success rate over 10 fresh trials, which becomes the finding's `reproducibility`. If the reduced attack's rate falls below half the original's, keep the last candidate that did not.

### 6.6 Findings
A finding is created when an attack objective holds or a `critical` forbidden check holds. Dedup key: `(agent version, category, objective check hash, vector)`; variants attach to the existing finding. Severity = max of the attack's base severity and a bump for irreversible world changes (`destructive`, `financial`, `external_comm` tool in the causal chain). `verify(finding)` re-runs the pinned reproducer `reproducibility[1]` times against the current agent version (and gateway policy if set); zero successes flips status to `verified`.

Tests: placement transforms; marker propagation; ddmin on a synthetic oracle with known minimal subset and injected flakiness; attacker loop with `FakeLLM` reaching the objective on round 3; dedup.

---

## 7. Policy engine and policy testing (`policy/`) — L8

### 7.1 Enforcement
`PolicyEngine.decide(prefix, proposed) -> GatewayDecision(action, rule_id, message, evidence)`: evaluate each rule's `when` with `evaluate_prefix`; the most severe violated rule wins; `undetermined` follows the policy's `fail` setting only for rules marked `strict`, otherwise allows. Pure and synchronous: target overhead under 2 ms for 50 rules, measured in a benchmark test. Anything needing a model (injection classifiers) is a `detector` node with its own latency budget, added in Phase 4 as [SUB] work behind the detector registry.

### 7.2 Offline policy testing
Given a policy and stored trajectories, no agent or model is re-run:
- For each trajectory, replay events in order, calling `decide` before each tool call and agent message. Record the first `block`.
- Attack trajectory (objective held): **blocked** if the first block comes at or before the earliest event in the objective's evidence. Block rate = blocked / attacks.
- Benign trajectory (episode passed): **broken** if any block occurs. False-positive rate = broken / benign.
- Per-rule breakdown, and a tradeoff table across rule subsets (greedy: add the rule with the best marginal block-per-false-positive).

This is a counterfactual approximation (the agent might have found another route after a block), so the closed loop ends with a live verification: re-run the pinned reproducers and the benign smoke suite with the policy enforced.

### 7.3 From finding to rule
`suggest_rule(finding) -> PolicyRule` is template-based on the objective type: `tainted_call` → block that tool when args carry untrusted markers or require approval; `tool_called` with arg matcher → argument constraint; `canary_leaked` / `egress` → output redaction or domain allowlist; honeytool → deny. A model only writes the description. The suggestion is then scored by 7.2 before it is shown.

Tests: decide truth tables; offline testing on hand-built trajectories with known block points; benchmark; suggest templates.
