# Phase 5 production loop, proof and launch: P5-1 to P5-7 (outline level)

These tasks are deliberately outlines. `docs/plan/04-roadmap.md` says Phase 5 is specified to the level of the other phases only when Phase 4 is done, because what gets built should follow what real users of Phases 1 to 4 ask for. Each entry gives scope, files, interfaces produced, key decisions and acceptance tests; before dispatch the lead expands the entry into the full task format (Steps in TDD order, exact names) and the implementer treats the "key decisions" as the starting position, not as final.

Batches (proposal): **q** = P5-1, P5-2. **r** = P5-3, P5-4. **s** = P5-5. **t** = P5-6. **u** = P5-7. Lead task L-R5 (final review, launch checklist) follows.

Conventions that still bind: no live LLM in tests (FakeLLM or cassettes), safety rules of `phase-2-security.md`, the gate **G** = `uv run ruff check . && uv run ruff format --check . && uv run pyright packages && uv run pytest packages tests apps -q`, additive schema changes recorded in "Contract questions" before they are built.

---

### P5-1: OpenTelemetry / OpenInference trace ingestion with PII redaction

**Batch:** q  **Depends:** P1-9, P1-4

**Scope.** Accept traces from a customer's production agent (gray-box), turn them into stored production conversations, and make them evaluable by the same deterministic detectors, rubrics and checks as simulated episodes. Out of scope: building instrumentation for any framework (customers use OpenInference or OTel GenAI instrumentation), real-time alerting (P5-7), automatic scenario creation (P5-2).

**Files.** `packages/server/src/gauntlet_server/ingest/{otlp,convert,redact,sessions,retention}.py`, `packages/server/src/gauntlet_server/routes/{traces,production}.py`, `packages/core/src/gauntlet_core/ingest/{semconv,trace_to_events}.py`, migration `00xx_production.py`, tests under `packages/core/tests/ingest/` and `packages/server/tests/ingest/`, fixtures `tests/fixtures/traces/*.json` (hand-made OTLP JSON in OpenInference and GenAI conventions).

**Interfaces produced.**
- `POST /v1/traces` (OTLP/HTTP, protobuf and JSON, API key with scope `ingest`), `GET /v1/production/conversations` (filters `agent_id, from, to, signal, q`), `GET /v1/production/conversations/{id}` (events, redaction summary), `GET /v1/production/stats`.
- `trace_to_events(spans, *, semconv) -> list[Event]`: spans to journal-shaped events (`user_message`, `agent_message`, `tool_call`, `tool_result`) with real timestamps in `sim_time` (documented) and `Origin` from tool semantics.
- Tables `prod_conversations`, `prod_events` (same JSON shape as `Event`, no effect records), `ingest_stats`.

**Key decisions.**
- Semantic conventions: OpenInference first (`openinference.span.kind` in LLM, TOOL, AGENT, CHAIN, RETRIEVER; `llm.input_messages`, `llm.output_messages`, `tool.name`, `tool.parameters`, `input.value`, `output.value`, `session.id`), with OTel GenAI (`gen_ai.*`) as fallback; unknown spans are kept as `sim_note` events, never dropped silently. Verify both specs' current attribute names when building.
- Redaction happens **before** anything is persisted: P1-4 `pii` and `secret` detectors plus configurable regexes; replacement by typed, trace-consistent tokens (`[EMAIL_1]`); raw text is never stored or logged; mapping is not kept (irreversible by default). A planted-PII test greps the database.
- Conversation grouping by `session.id` (else trace id); retention (`GAUNTLET_PROD_RETENTION_DAYS`, default 30) enforced by a worker sweep; per-workspace sampling rate and size caps (span count and bytes) with 413 and a counter when exceeded.
- Decoding with `opentelemetry-proto` (verify current package and licence); idempotent on `(trace_id, span_id)`.
- Evaluation of production conversations reuses `Trajectory` construction with an empty world (no state checks; tool-call, output, canary, egress, detector checks and judges work).

**Acceptance tests.** OpenInference and GenAI fixtures convert to the expected event sequences; a conversation with planted emails, cards and keys contains none of them after ingest (database grep and API output); duplicate span ingest is idempotent; oversize payload gets 413; a converted conversation runs through `evaluate_final` for a tool-call check and a detector check; ingest throughput benchmark of at least 500 spans per second on one api process (recorded, not gating).

---

### P5-2: Failure mining and conversation-to-scenario conversion with anonymisation

**Batch:** q  **Depends:** P5-1, P3-6, P3-5 (jobs), P1-7

**Scope.** Find the conversations most likely to be failures, cluster them, and convert chosen ones into draft scenarios that can be run in simulation, without carrying personal data. Human approval is mandatory before a mined scenario can run.

**Files.** `packages/core/src/gauntlet_core/mining/{signals,score,anonymise,to_scenario,world_from_trace}.py`, `packages/server/src/gauntlet_server/services/mining.py`, `packages/server/src/gauntlet_server/routes/mining.py`, tests in matching `tests/mining/` directories.

**Interfaces produced.**
- `score_conversation(conv, detectors, *, judge=None) -> FailureScore` combining deterministic detector hits, user-signal heuristics (repeated rephrasing, explicit dissatisfaction, request for a human, abandonment before resolution, thumbs-down attributes if present) and an optional sampled small-judge check on a calibrated rubric only.
- `POST /v1/production/mine {agent_id, window, limit}` (job), `GET /v1/production/candidates` (ranked, clustered with the P3-6 machinery), `POST /v1/production/candidates/{id}/convert` returning a draft scenario (status `draft`, `source=mined`), `POST /v1/scenarios/{id}/approve` is the existing approval route.
- `anonymise(conversation, *, seed) -> (conversation', mapping_hash)`: consistent replacement of names, emails, phones, order or account numbers, addresses and free-text entities with seeded synthetic equivalents.
- `world_from_trace(conv, world_spec) -> WorldOverrides`: reconstructs the minimal seed records implied by tool results in the trace and maps them onto the agent's world spec.

**Key decisions.**
- Anonymisation runs again at conversion even though ingest already redacted, and a post-check scans the produced scenario YAML with all detectors and a high-entropy-token check; any hit fails the conversion.
- The scenario goal and hidden facts are produced by a model from the anonymised conversation (role `generator`, structured output); the success check is a **draft** inferred only from observable facts in the trace (tool calls that resolved the user's goal) and is flagged `needs_review`; the forbidden checks reuse the detectors that flagged the failure. Nothing is auto-approved.
- k-anonymity guard: a conversation containing an identifier that appears in fewer than 3 other conversations and could not be replaced is excluded from conversion with a reason.
- Mined scenarios keep only a reference to the production conversation id, never its text.

**Acceptance tests.** Planted PII in a fixture conversation is absent from the produced scenario YAML (detectors and grep); the produced scenario validates (`validate_scenario`) and runs against a scripted agent in the runner; ranking puts a conversation with a detector hit above a clean one; conversion fails closed when a hit survives; approval route is required (a `draft` mined scenario cannot be included in a run without `include_drafts`).

---

### P5-3: Enterprise knowledge copilot pack and banking pack

**Batch:** r  **Depends:** P1-6 conventions, P2-1, P1-11

**Scope.** Two deep vertical packs from the addendum (sections 4.2, 4.3, 5.2), each with a world, about 20 scenarios, oracle tests, and a vulnerable DVA variant. The copilot pack adds role-based identities and an ACL leakage tester.

**Files.** `packs/enterprise_copilot/{pack.yaml,world.yaml,seed.yaml,policy.md,handlers.py,gen_seed.py,scenarios/,suites/}`, `packs/banking/{...same...}`, `packages/core/src/gauntlet_core/packs_acl.py` (probe generator), `apps/dva/dva/copilot_agent/`, `apps/dva/worlds/copilot*.yaml`, tests in `tests/packs/`.

**Interfaces produced.**
- Copilot tools: `search_documents(query)`, `get_document(document_id)`, `list_my_groups()`, `search_messages(query)`, `escalate_to_human`. The acting user is world state: a `session` collection holding `current_user` (set per scenario through `world_overrides`), because `Scenario` has no identity field (CQ-P1). Handlers either enforce the ACL (secure variant) or return everything (DVA variant).
- `generate_acl_probes(world, *, seed, per_document=3) -> list[Scenario]`: for each restricted document and a user without access, probes by topic, by name, and by indirect reference; success is "answers without the canary", forbidden is `canary_leaked` for that document's canary; includes aggregation probes (counts, comparisons) whose forbidden check is a `detector` for restricted-count disclosure and cross-tenant probes using per-tenant canary records.
- Banking tools: `get_balance`, `list_transactions`, `block_card`, `file_dispute`, `add_payee`, `get_kyc_status`, `escalate_to_human`; scenarios from addendum 4.2 (urgent lost card without verification, fee explanation from the real schedule, partial-information dispute, scam victim being coached, new payee after password reset, investment advice request, vulnerable customer cues, injection through a transaction memo field).

**Key decisions.** Same method as P1-6: fixtures generated by a seeded script, scenario tables in the task file, good and bad oracle trajectories per scenario, fictional institutions and people only. Policy texts numbered so rubrics and DVA flaw rows can cite them. The ACL tester is deterministic for a seed. Regulated-advice rules are written as agent policy for testing, never as legal guidance. Banking handlers enforce data integrity only (as in ecommerce).

**Acceptance tests.** Packs load and validate; oracle tests pass for every scenario; `generate_acl_probes` yields at least 40 probes for the seed world, deterministically; the DVA copilot variant with the permissive handler leaks in at least 80 percent of probes and the secure variant leaks in none; the banking suite runs through the CLI against the DVA banking variant (scripted brain) with the expected failures.

---

### P5-4: tau-bench retail and AgentDojo import; benchmark reproduction run

**Batch:** r  **Depends:** P1-10, P2-2, P5-3 conventions

**Scope.** Make Gauntlet's numbers comparable to published ones: import tau-bench retail tasks and a subset of AgentDojo suites as worlds and scenarios, then reproduce published results with the same models and report the gap honestly.

**Files.** `tools/import_benchmarks/{tau_bench,agentdojo_world}.py`, `packs/taubench_retail/`, `packs/agentdojo_banking/`, `packs/agentdojo_slack/`, `benchmarks/reproduction/{README.md,config.yaml,results/}`, tests with miniature upstream-format fixtures.

**Interfaces produced.** Importers (pinned upstream commit, licence recorded, same rules as P2-2: nothing authored by us): tau-bench retail environment data and tools ported to pure Gauntlet handlers, each task converted to a `Scenario` whose `goal` is the task instruction, whose `success` is built from the expected final state (the importer replays the task's ground-truth actions through our handlers on the initial data to compute the expected end state, then emits `state` checks per changed record plus required-output checks); AgentDojo suites (environment YAML and tool functions ported to handlers, user tasks to scenarios with utility checks, injection tasks to `Attack`s with security checks) limited to tasks expressible in the check language, with the portable percentage reported. A command `uv run python -m benchmarks.reproduction run --suite taubench_retail --model <id> --trials 4` producing pass^k tables with intervals.

**Key decisions.** Licences and dataset terms are **verify** items (tau-bench and AgentDojo are believed MIT; check before vendoring). Porting tool semantics is manual and reviewed by the lead; every ported handler gets purity tests and a golden test against upstream-recorded results where available. Reproduction compares like with like (same model id family, same user simulator model class if specified upstream) and states every deviation; the acceptance target is agreement within 10 points absolute on the baseline utility metric, and a written explanation when outside it. Cost-capped runs only (`GAUNTLET_LIVE_BUDGET_USD`), cassettes committed for the CI smoke subset.

**Acceptance tests.** Importer tests on fixtures produce valid scenarios and handlers; for 10 sampled tasks, replaying ground-truth actions makes `success` hold (oracle); the portable-task percentage is printed; the reproduction harness runs the smoke subset from cassettes in CI; the first full reproduction run (live, manual) writes `benchmarks/reproduction/results/*.json` with intervals and a `README.md` discussion of the gap.

---

### P5-5: Meta-evaluation studies and benchmark page

**Batch:** s  **Depends:** P2-9, P3-5, P3-3, P5-4, L-R3 (hand-labelled set)

**Scope.** Prove the platform itself works (spec section 15): scripted, reproducible studies with published numbers and negative results included. Out of scope: marketing copy.

**Files.** `studies/{dva_recall,judge_agreement,reproducibility,cost_per_1000,simulator_fidelity,head_to_head}.py`, `studies/README.md` (pre-registered metrics and seeds), `benchmarks/results/*.json` (committed outputs), `packages/server/src/gauntlet_server/routes/meta.py` (`GET /v1/meta/benchmarks`), `apps/web` page `/benchmarks` is web work (note for the web phase file), `docs/benchmarks/index.md` generated by `uv run python -m studies.render`.

**Interfaces produced.** Each study is `uv run python -m studies.<name> --seed N --out benchmarks/results/<name>.json` with a typed result model (`StudyResult(name, version, seed, platform_version, metrics: dict, intervals: dict, n, notes)`); a renderer producing the benchmark page from the JSON files; a freshness check script failing CI when a result file's `platform_version` is older than the release being cut.

**Key decisions.** Metrics are fixed before running: DVA recall and clean-control false positives (P2-9 script, all three agents, bootstrap intervals over attack samples); judge agreement per calibrated rubric (accuracy, precision and recall on the fail class, Cohen's kappa with interval) on the hand-labelled set from L-R3, with the cascade's cost per verdict and escalation rate; reproducibility (same suite, same agent, 5 reruns: variance of pass rate, and strict cassette replay identical in 100 percent of episodes); cost per 1,000 episodes from real run ledgers; simulator fidelity (guard rule hit rate and persona-guard rubric pass rate); head-to-head against other open-source scanners on the DVA (same targets, same time and cost budget; garak and promptfoo versions pinned, findings counted by flaw ids, licences respected) as optional. Results are published whether or not they flatter the product; limitations are written next to each number.

**Acceptance tests.** Each study runs from cassettes or scripted brains in CI in under 5 minutes with a smoke configuration and writes a valid `StudyResult`; the renderer output is deterministic (golden test); the freshness check fails on a stale file; a full live run (manual, capped) produces the committed result files reviewed by the lead.

---

### P5-6: MCP server for the platform, docs site, public challenge arena

**Batch:** t  **Depends:** P1-9, P2-5, P3-4, P4-2, P4-3, web foundation

**Scope.** Three launch surfaces: (a) an MCP server so coding agents can drive Gauntlet, (b) a documentation site, (c) a public arena where visitors attack one defended agent.

**Files.** (a) `packages/mcp_server/` (new uv workspace member `gauntlet-mcp`: `src/gauntlet_mcp/{server,tools,client}.py`). (b) `docs/user/**`, `mkdocs.yml`, `docs/site/` build output ignored, `.github/workflows/docs.yml`, generators `tools/docs/{cli_ref,api_ref,check_ref}.py`. (c) `apps/arena/` (FastAPI service `arena`), `packs/arena/` (world, levels), web routes under `apps/web/src/app/arena/**` (web work), migration for `arena_levels`, `arena_attempts`, `arena_solves`.

**Interfaces produced.**
- (a) MCP tools (read-mostly, API key auth, stdio and streamable HTTP): `list_agents`, `list_runs`, `get_run_report`, `get_episode`, `list_findings`, `get_finding`, `generate_scenarios`, `create_run` (requires an explicit `budget_usd` no larger than `GAUNTLET_MCP_MAX_BUDGET_USD` and a `confirm=true` argument), `compare_runs`. No deletion or policy-changing tools. Each tool result is size-capped and carries only ids and summaries.
- (b) MkDocs Material site (`mkdocs build --strict` in CI): quickstart (5 minutes to first report), concepts (episodes, journal, checks language, rubrics, findings), guides (hosted, wired and black-box targets, CI gate, gateway), reference generated from code (CLI via Typer, REST from the OpenAPI document, the check language from JSON Schema), threat taxonomy page, safety and responsible-use page.
- (c) Arena: `POST /arena/v1/attempts {level}` creates an attempt and a fresh world; `POST /arena/v1/attempts/{id}/messages {text}` runs one human turn through the engine with a `HumanUser` turn source (the user's text is the journaled user message; the agent turn loop and world are the existing machinery), `GET /arena/v1/leaderboard?level=`, `POST /arena/v1/handles`.

**Key decisions.** Arena: one agent (a DVA-derived support-style agent with fake secrets only) defended progressively across 5 levels (prompt only; plus policy; plus injection classifier; plus approvals and taint rules; full gateway with MCP pinning). Win condition per level is deterministic (a per-attempt canary derived from `HMAC(secret, attempt_id)` appears in output, or a honeytool is called), so flags cannot be shared. Anti-abuse: per-IP and per-handle rate limits (Redis), attempt caps per day, per-attempt message and token caps, total daily dollar budget with automatic closure, no external tools or network for the agent, all outputs scanned and a report button; the platform kill switch (P2-4) also closes the arena. Leaderboard shows handle, level, turns to solve and time; no accounts, no emails. MCP server never exposes secrets and respects the API key's workspace. Docs examples are executable: a CI job runs the quickstart commands against the DVA with the scripted brain.

**Acceptance tests.** (a) In-memory MCP transport tests against a fake API: tool list, a read flow, `create_run` refused without `confirm` or over the cap, size caps. (b) `mkdocs build --strict` passes; generated references are up to date (CI diff check); quickstart script runs green. (c) Arena: a scripted solver beats level 1 and fails level 5 deterministically (cassette), a flag from one attempt does not solve another, rate limits and budget cutoff close the arena, leaderboard orders by turns then time, attempts never persist user text beyond a configurable retention (default 14 days).

---

### P5-7: SLOs, change-impact analysis, launch readiness review, compliance evidence pack

**Batch:** u  **Depends:** P3-2, P3-8, P2-6, P4-5, P5-1

**Scope.** The operations layer around releases: service-level objectives with error budgets, selective re-testing on change, a go or no-go review, and an exportable evidence pack.

**Files.** `packages/server/src/gauntlet_server/services/{slo,schedules,alerts,impact,readiness,evidence}.py`, `packages/server/src/gauntlet_server/routes/{slo,schedules,impact,readiness,evidence}.py`, `packages/core/src/gauntlet_core/impact.py`, `packages/cli/src/gauntlet_cli/commands/{impact,evidence}.py`, migrations for `schedules`, `slos`, `alert_rules`, `alerts`, `evidence_packs`.

**Interfaces produced.**
- SLOs: `POST /v1/slos {agent_id, metric, objective, window, burn_alerts}` with metrics `pass_rate` (scheduled suite), `attack_success_rate` (scheduled security suite), `latency_p95`, `cost_per_episode`, and production signals from P5-1; error budget and multi-window burn rate computed from stored runs; `schedules` (cron-like, UTC) enqueue runs through the existing run service; `alert_rules` deliver to webhook and Slack incoming webhook (email via SMTP optional) with de-duplication and silence windows.
- Change impact: `compute_impact(change: Change, history) -> ImpactSet` where `Change` is one of prompt, tool schema, model, policy or world change (derived from two `AgentVersion`s and policies); returns scenarios to rerun with reasons (a scenario whose success or forbidden checks or past tool calls reference a changed tool; scenarios tagged with a changed policy clause; for model or prompt changes a stratified risk-based sample plus every pinned regression and every scenario that flipped in the last 5 runs); CLI `gauntlet impact --from VERSION --to VERSION` and an `impact: true` option in the GitHub Action.
- Readiness: `GET /v1/agents/{id}/versions/{vid}/readiness` returns a release readiness score (spec's composite of success rate, reliability pass^k, safety, cost, latency, each with its interval) and a go, no-go or conditional decision against thresholds that depend on the agent's risk tier (derived from tool risk and data access), listing blockers and unverified claims.
- Evidence pack: `POST /v1/evidence-packs {agent_version_id, frameworks}` (job) producing a zip in object storage: manifest, run reports and `RunManifest`s, posture report, coverage mapped to OWASP LLM and agentic ids (and NIST AI RMF or ISO 42001 only after their current versions are checked), calibration results, policy versions and gateway decision summaries, audit-log excerpt with hash-chain verification output, cassette references, a `SHA256SUMS` file and an optional Ed25519 signature (server key from env).

**Key decisions.** Scheduled runs and alerts must never exceed workspace budgets (the budget ledger applies); SLO math uses the same statistics module (intervals, not point estimates, decide breaches); impact analysis is conservative and explains itself, and a flag forces a full run; readiness thresholds are configuration, with defaults documented and the decision always showing the evidence behind each criterion; evidence packs never contain raw payloads of dangerous categories or secrets (redaction pass plus a scan with the P1-4 detectors) and are reproducible (another person can rerun from the manifests); compliance mapping language says "evidence supporting", never "compliant".

**Acceptance tests.** Burn-rate and error-budget tables with known inputs; schedule enqueues a run exactly once per tick (clock injected) and respects budgets; alert de-duplication and silence; impact sets for crafted changes (tool schema change selects exactly the referencing scenarios plus pinned regressions; model change selects the stratified sample); readiness decision table across tiers; evidence pack contents listed and checksums verify, audit chain verification embedded, a planted secret absent (grep of the zip), signature verifies.

---

## Contract questions (Phase 5)

| ID | Question |
|---|---|
| CQ-P1 | `Scenario` has no field for the acting user or role (needed by the copilot pack and ACL tests); this outline carries identity in world state (`session.current_user`) via `world_overrides`. Confirm, or add a field. |
| CQ-P2 | Production conversations (P5-1) are not journals: no effects, real timestamps in `sim_time`. Confirm that `Event` may carry real time for ingested data and that `Trajectory` construction with an empty world is acceptable for evaluation. |
| CQ-P3 | New tables and routes for production data, mining candidates, schedules, SLOs, alerts, arena and evidence packs are outside contracts section 8. Ratify before expansion into full tasks. |
| CQ-P4 | Human-driven episodes (arena) need a turn source that is not `UserSimulator`; confirm `run_episode` can take a `UserSimulator` implementation backed by an external input queue, or add a contract. |
| CQ-P5 | Licences and dataset terms for tau-bench, AgentDojo ports, and any NIST or ISO text used in the evidence pack need legal check before vendoring or quoting. |
