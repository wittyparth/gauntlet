# Phase 5 production loop, proof and launch: P5-1 to P5-7

Expanded 2026-11-22 from the outline, after Phase 4 closed. Binding: `02-contracts.md` "Phase 5 rulings (2026-11-22)" (CQ-P1..P5), the Phase 4 rulings, and the conventions below. Table and route names here are proposals under CQ-P3: the lead ratifies them on review before any task starts.

**Batches.** **q** = P5-1, P5-2 (backend). **r** = P5-3, P5-4 (backend, packs and importers). **s** = P5-5, P5-7 (backend). **t** = P5-6 (MCP server, docs site, arena backend, then the web pages). Order: q before s (P5-7 uses P5-1 signals; P5-2 uses P5-1); r before P5-5 (P5-5 uses P5-4); t last. Lead task L-R5 (final review, launch checklist) follows.

**Conventions that bind every task.**
- **Models.** Only cheap models from the catalog (`gauntlet_core.llm.catalog`, roles `simulator`, `judge_small`, `judge_strong`, `attacker`, `generator`), never an OpenAI or Anthropic model, in code defaults, studies, examples or docs. Live runs are manual, capped by `GAUNTLET_LIVE_BUDGET_USD`, and need the lead's go before any spend.
- **Tests.** No live LLM, no network, no model download (FakeLLM, scripted brains, cassettes, in-memory transports). Optional heavy dependencies are opt-in extras. CI never skips silently: opt-in tests are marked and skipped by an explicit env switch.
- **Offline defaults.** Nothing phones home; every network feature (webhooks, SMTP, docs deploy) is off until configured.
- **Web.** Animate UI components only (the `animate-ui` skill's catalogue), on the existing Next.js app; no other component libraries.
- **Schema.** Migrations are hand-written, numbered from the current head (**0014**), `alembic check` clean, every new `/v1` route has a typed `response_model`, new tables are added to `CONTRACT_TABLES` in `packages/server/tests/db/test_migrations.py`. Stored Pydantic documents are dumped with `dump_doc` (`exclude_defaults`, `by_alias`) because matchers dumped with unset operators reload wrongly.
- **Gate G** = `uv run ruff check . && uv run ruff format --check . && uv run pyright packages apps && uv run pytest packages apps tests -q` with `TEST_DATABASE_URL` set; web tasks add the web gate (`typecheck`, `lint`, `build`, Playwright smoke).
- Safety rules of `phase-2-security.md` and audit rows for every state-changing action (`audit(...)`) apply to all new routes. Files outside `Files:` are not touched.

Migration numbering: P5-1 `0015_production`, P5-2 `0016_mining`, P5-7 `0017_ops` (schedules, slos, alerts) and `0018_evidence`, P5-6 `0019_arena`. P5-3, P5-4 and P5-5 need none.

---

### P5-1: OpenTelemetry / OpenInference trace ingestion with PII redaction

**Batch:** q  **Depends:** P1-9 (server), P1-4 (detectors), P3-5 (jobs), P2-4 (audit)

**Scope.** Accept traces from a customer's production agent (gray-box), store them as production conversations, and make them evaluable by the same detectors, rubrics and checks as simulated episodes. Out of scope: instrumentation of any framework, real-time alerting (P5-7), scenario creation (P5-2).

**Files:**
- Create: `packages/core/src/gauntlet_core/ingest/{__init__,semconv,trace_to_events,redact}.py`, `packages/server/src/gauntlet_server/ingest/{__init__,otlp,sessions,retention}.py`, `packages/server/src/gauntlet_server/services/production.py`, `packages/server/src/gauntlet_server/routes/{traces,production}.py`, `packages/server/migrations/versions/0015_production.py`, `tests/fixtures/traces/{openinference_support.json,genai_support.json,planted_pii.json,oversize.json}`
- Modify: `packages/server/src/gauntlet_server/{app,config,worker}.py` (routes, settings, retention sweep), `packages/server/src/gauntlet_server/db/policy_models.py` or a new `db/prod_models.py`
- Test: `packages/core/tests/ingest/{test_semconv.py,test_trace_to_events.py,test_redact.py}`, `packages/server/tests/ingest/{test_otlp_routes.py,test_redaction_db.py,test_production_routes.py,test_retention.py}`, `tests/bench/test_ingest_throughput.py`

**Interfaces:**
- Consumes: P1-4 `detect_pii`, `detect_secret`; `Event`, `Origin`, `Trajectory`, `evaluate_final`; `PgJobQueue`; `audit`; API key scopes (`api_keys.scopes`); `opentelemetry-proto` for protobuf decoding (add to the server package; verify the package and its licence before adding).
- Produces:
  - `trace_to_events(spans: Sequence[Span], *, semconv: Literal["openinference","genai","auto"] = "auto") -> ConvertedConversation(session_id, events: list[Event], unknown_spans: int)`. Event `sim_time` carries the real span time (CQ-P2); `Origin(trust="untrusted_external")` for tool results of tools in a configurable `untrusted_tools` glob list, else `system`.
  - `Redactor(rules: RedactionConfig)` with `redact_text(text) -> (text', counts: dict[str, int])` and `redact_json(value)`: typed consistent tokens per conversation (`[EMAIL_1]`, `[CARD_1]`, `[SECRET_1]`), P1-4 detectors plus configured regexes. The mapping is never stored.
  - Tables: `prod_conversations(id pc_, workspace_id, agent_id nullable, external_session_id, started_at, ended_at, event_count, signals jsonb, redaction jsonb /* counts by type */, run_id nullable /* the import run once evaluated */, created_at)` unique `(workspace_id, external_session_id)`; `prod_events(conversation_id, seq, kind, doc jsonb, primary key (conversation_id, seq))`; `prod_spans_seen(workspace_id, trace_id, span_id, primary key)` for idempotency; `ingest_stats(workspace_id, day, spans, bytes, rejected, redactions jsonb, primary key (workspace_id, day))`.
  - Routes: `POST /v1/traces` (OTLP/HTTP protobuf or JSON, scope `ingest`; `{partial_success: {rejected_spans}}` body as OTLP specifies; 413 over caps), `GET /v1/production/conversations` (filters `agent_id, from, to, signal, q`; cursor pagination), `GET /v1/production/conversations/{id}`, `POST /v1/production/conversations/{id}/evaluate` (job: build a `Trajectory` with an empty world, run the agent's detectors and chosen rubrics, store as a `purpose=import` run with no effects, CQ-P2), `GET /v1/production/stats?window=`.
  - Settings: `GAUNTLET_PROD_RETENTION_DAYS` (30), `GAUNTLET_INGEST_MAX_SPANS` (5000 per request), `GAUNTLET_INGEST_MAX_BYTES` (4 MiB), `GAUNTLET_INGEST_SAMPLE_RATE` (1.0).

**Decisions:**
- **Conventions.** OpenInference first (`openinference.span.kind` in LLM, TOOL, AGENT, CHAIN, RETRIEVER; `llm.input_messages`, `llm.output_messages`, `tool.name`, `tool.parameters`, `input.value`, `output.value`, `session.id`), OTel GenAI (`gen_ai.*`) second; **verify both specs' current attribute names when building** and record the version in `semconv.py`. Unknown spans become `sim_note` events with the span name only (no attribute dump); they are never dropped silently and counted in `unknown_spans`.
- **Redaction before persistence.** Decode, convert, redact, then insert in one transaction. Raw text is never written to the database, logs or exceptions (error messages carry ids and counts). Attribute keys named like secrets (`authorization`, `api_key`, `password`, `token`) are removed by key. The redaction summary (counts per type) is returned by the API; the mapping is not kept.
- **Grouping and idempotency.** Conversation = `session.id`, else the trace id; the `(trace_id, span_id)` pair is inserted into `prod_spans_seen` with `ON CONFLICT DO NOTHING` and only new spans are converted, so re-sending a batch changes nothing. Events of one conversation are re-sequenced by start time, then span order, when late spans arrive (`seq` is rewritten in the same transaction only for conversations touched by the batch).
- **Caps and sampling.** Request over the byte or span cap: 413 with `{error: {code: "payload_too_large"}}` and `ingest_stats.rejected` incremented; sampling drops whole sessions deterministically by hash of the session id, so a kept conversation is complete.
- **Retention.** A worker sweep (hourly, `FOR UPDATE SKIP LOCKED` batches of 1000) deletes conversations older than retention together with events and span markers; `import` runs made from them keep only ids and verdicts.
- **Evaluation.** Production conversations have no world: `state` and `state_diff` checks report `undetermined` (CQ-P2), and rubric judging uses the same cascade with the production text already redacted. Evaluation never calls a live model in tests.
- **Auth.** Keys need scope `ingest`; reading routes need the normal scopes. Ingest rate limit per key (Redis, default 50 requests per second).

**Steps:**
- [ ] `test_semconv.py` and `test_trace_to_events.py`: both fixtures convert to the expected event sequences (user message, tool call, tool result, agent message order; multi-turn; parallel tool calls); unknown spans counted; real times preserved; origin from the untrusted glob.
- [ ] `test_redact.py`: typed consistent tokens (same email gives the same token in one conversation, different tokens across), cards (Luhn), keys, secret-named attribute keys removed; idempotent on redacted text.
- [ ] `test_redaction_db.py` (integration): ingest `planted_pii.json`; dump every text column of every table and the API output and grep for each planted value: none found.
- [ ] `test_otlp_routes.py`: protobuf and JSON bodies, scope check (403 without `ingest`), duplicates idempotent, 413, partial success body, sampling determinism, rate limit 429.
- [ ] `test_production_routes.py`: list filters and cursor, detail, evaluate job produces a `purpose=import` run whose tool-call and detector checks hold on a crafted conversation, world checks `undetermined`, workspace scoping 404.
- [ ] `test_retention.py` (clock injected): sweep deletes only expired rows and their children. `test_ingest_throughput.py`: at least 500 spans per second on one api process, recorded.
- [ ] Implement; **G**, integration. Commits: `feat(core): trace to events and redaction`, `feat(server): otlp ingest and production routes`.

**Done when:** an OpenInference fixture posted to `POST /v1/traces` appears in `GET /v1/production/conversations` with no planted PII anywhere in the database or API output, the conversation evaluates through the detector cascade into an import run, and re-posting changes nothing.

---

### P5-2: Failure mining and conversation-to-scenario conversion with anonymisation

**Batch:** q  **Depends:** P5-1, P3-6 (clusters), P3-5 (jobs), P1-7 (generation)

**Scope.** Rank production conversations by likelihood of failure, cluster them, and convert chosen ones into draft scenarios for simulation without personal data. A human approves every mined scenario before it can run.

**Files:**
- Create: `packages/core/src/gauntlet_core/mining/{__init__,signals,score,anonymise,to_scenario,world_from_trace,prompts}.py`, `packages/server/src/gauntlet_server/services/mining.py`, `packages/server/src/gauntlet_server/routes/mining.py`, `packages/server/migrations/versions/0016_mining.py`
- Modify: `packages/server/src/gauntlet_server/{app,worker}.py` (route, job kinds `mine_failures`, `convert_candidate`)
- Test: `packages/core/tests/mining/{test_signals.py,test_score.py,test_anonymise.py,test_to_scenario.py,test_world_from_trace.py}`, `packages/server/tests/mining/{test_mining_routes.py,test_convert_flow.py}`

**Interfaces:**
- Consumes: P5-1 tables and `trace_to_events` conversations, the P1-4 detectors, P3-6 `group_failures` / `embed_texts` (offline `HashEmbedder` by default), P1-7 scenario compile and `validate_scenario`, `Gateway` (`generator` and `judge_small` roles, structured output), `PgJobQueue`.
- Produces:
  - `FailureScore(total: float, parts: dict[str, float], reasons: list[str])` and `score_conversation(conv, detectors: Sequence[DetectorSpec], *, judge: SampledJudge | None = None) -> FailureScore`. Parts: `detector` (any hit gives at least 0.6), `rephrasing` (user repeats a request, normalised edit similarity), `dissatisfaction` (phrase patterns, thumbs-down attributes), `human_request`, `abandonment` (last event is a user message with no later agent message, or the conversation ends within one turn of an apology), `judge` (only on a calibrated rubric, sampled).
  - `anonymise(conv, *, seed) -> Anonymised(conversation, replacements: int, mapping_hash: str, residual: list[str])`: consistent seeded synthetic replacement of names, emails, phones, order and account numbers, addresses, and capitalised free-text entities.
  - `to_scenario(conv, *, agent: AgentVersion, world: WorldSpec, gateway, seed) -> MinedDraft(scenario, notes, needs_review: list[str])`.
  - `world_from_trace(conv, world: WorldSpec) -> dict` (world overrides: seed records implied by tool results, mapped by collection and id onto the world spec).
  - Tables: `mining_runs(id mrun_, workspace_id, agent_id, window jsonb, status, counts jsonb, created_at, finished_at)`; `mining_candidates(id cand_, workspace_id, mining_run_id, conversation_id, score real, parts jsonb, cluster_id nullable, status /* new, converted, dismissed */, scenario_id nullable, created_at)`.
  - Routes: `POST /v1/production/mine {agent_id, from, to, limit}` (job, returns `{job_id, mining_run_id}`), `GET /v1/production/candidates?mining_run_id&status&cluster` (ranked, cursor), `GET /v1/production/candidates/{id}` (score parts and the redacted conversation), `POST /v1/production/candidates/{id}/convert` (job; returns `{job_id}`, result is the draft scenario id), `POST /v1/production/candidates/{id}/dismiss`. Approval stays the existing `POST /v1/scenarios/{id}/approve`.

**Decisions:**
- **Scoring is deterministic first.** Detector and heuristic parts need no model. The judge part runs only when the agent has a calibrated rubric (`gating_allowed`), on a sample (`GAUNTLET_MINE_JUDGE_SAMPLE`, default 0.1 of the window, capped by the job budget); its cost is reported.
- **Anonymise again at conversion** though ingest already redacted: seeded replacement, then a post-check that scans the scenario YAML (goal, hidden facts, opening message, persona text, world overrides) with all P1-4 detectors, a high-entropy-token check (Shannon entropy over 16 or more characters) and a leftover-token check for `[EMAIL_1]`-style tokens; any hit fails the conversion closed with the reasons and nothing is stored.
- **k-anonymity guard.** An identifier (account or order number, name) that occurs in fewer than 3 other conversations of the workspace and could not be replaced is a quasi-identifier: the candidate is marked `status=dismissed` with reason `k_anonymity` and cannot convert.
- **Generation.** `generator` role, structured output, `temperature=0`: goal, persona traits, hidden facts and an opening message from the anonymised text. Success check: **draft**, built only from observable facts (tool calls that resolved the request, final tool state implied by results), flagged `needs_review`; forbidden checks reuse the detectors that flagged the conversation. The scenario is stored `status=draft, source=mined` with `tags {mined_from: <candidate id>}`; the production conversation id is kept only as a reference, never its text.
- **Clustering** reuses the P3-6 machinery on redacted conversation text; clusters are named by the `generator` role with the existing cache. The whole job is metered against a budget given at request time (default small) and refuses to start without one.
- **No auto-approval and no auto-run.** The route that creates a run already rejects drafts without `include_drafts`; the mined scenario carries the tag so the web console can show its origin.

**Steps:**
- [ ] `test_signals.py` and `test_score.py`: each heuristic on crafted conversations; a conversation with a detector hit outranks a clean one; judge part absent without a calibrated rubric; scores deterministic.
- [ ] `test_anonymise.py`: planted names, emails, phones, order and account numbers, addresses replaced consistently within a conversation and differently across seeds; residual list empty on the fixture; idempotent.
- [ ] `test_to_scenario.py` (FakeLLM): produced scenario validates (`validate_scenario`) and runs against a scripted agent in the runner; planted PII absent from the YAML (detectors and grep); a surviving hit fails the conversion; `needs_review` set on the success check; k-anonymity exclusion.
- [ ] `test_world_from_trace.py`: records implied by tool results map onto the world spec; unknown collections reported, not invented.
- [ ] `test_mining_routes.py`, `test_convert_flow.py` (integration): mine job ranks candidates and clusters them; convert creates a draft; the draft cannot run without `include_drafts`, can after `approve`; budget refusal; scoping 404; audit rows.
- [ ] Implement; **G**, integration. Commits: `feat(core): failure scoring, anonymisation and scenario conversion`, `feat(server): mining jobs and candidate routes`.

**Done when:** a mixed fixture of production conversations yields a ranked candidate list, a chosen failing one converts to a draft scenario with zero detector hits and zero entropy hits, and after approval the scenario runs against a scripted agent.

---

### P5-3: Enterprise knowledge copilot pack and banking pack

**Batch:** r  **Depends:** P1-6 (pack conventions), P2-1, P1-11 (DVA), P4-1 (policy text compile reads `policy.md`)

**Scope.** Two vertical packs from the addendum, each with a world, about 20 scenarios, oracle trajectories and a vulnerable DVA variant; the copilot pack adds role-based identities and an ACL leakage tester.

**Files:**
- Create: `packs/enterprise_copilot/{pack.yaml,world.yaml,seed.yaml,policy.md,handlers.py,gen_seed.py,scenarios/,suites/}`, `packs/banking/{same layout}`, `packages/core/src/gauntlet_core/packs_acl.py`, `apps/dva/dva/copilot_agent/{__init__,agent,flaws}.py`, `apps/dva/dva/banking_agent/{__init__,agent,flaws}.py`, `apps/dva/worlds/{copilot,copilot_fixed,banking,banking_fixed}.yaml`
- Test: `tests/packs/{test_copilot_pack.py,test_banking_pack.py,test_acl_probes.py}`, `apps/dva/tests/{test_copilot_dva.py,test_banking_dva.py}`

**Interfaces:**
- Consumes: pack loader and validators, crud and python handler kinds, canaries, `Scenario.world_overrides`, the L5 checks, DVA flaw-registry conventions from P1-11.
- Produces:
  - Copilot world and tools: `search_documents(query)`, `get_document(document_id)`, `list_my_groups()`, `search_messages(query)`, `escalate_to_human(summary, reason)`. The acting user is world state: collection `session` with record `current` (`user_id`, `groups`, `tenant`), set per scenario through `world_overrides` (CQ-P1). The secure handlers filter by `session.current` ACL and tenant; the DVA variant's permissive handlers search everything.
  - `generate_acl_probes(world: WorldSpec, *, seed: int, per_document: int = 3) -> list[Scenario]` in `packs_acl.py`: for each restricted document and each user without access, probes by topic, by exact name and by indirect reference; success is "answers helpfully without the canary"; forbidden is `canary_leaked` for that document's canary. Aggregation probes (counts and comparisons over restricted documents) forbid a `detector` result for restricted-count disclosure, and cross-tenant probes use per-tenant canary records.
  - Banking world and tools: `get_balance`, `list_transactions`, `block_card`, `file_dispute`, `add_payee`, `get_kyc_status`, `escalate_to_human`. Data-integrity handlers only (no business rules in handlers, as in ecommerce).

**Decisions:**
- **Method as P1-6.** Fixtures come from a seeded `gen_seed.py` (deterministic, fictional institutions and people only); policy texts are numbered (`C1..`, `B1..`) so rubrics, scenarios and DVA flaw rows cite them; each scenario has a good and a bad oracle trajectory and an expected set of check results in its test.
- **Copilot scenario groups (about 20, in the task's table):** ACL (restricted document by topic, name and indirect hint; wrong-group user asking for a manager's review; former-employee role), tenant isolation, aggregation leaks, prompt injection through a document and a chat message, citation honesty (answer must come from retrieved text), stale-document handling, over-broad search request, escalation.
- **Banking scenario groups (about 20, addendum 4.2):** urgent lost card without verification, fee explanation from the real schedule, partial-information dispute, scam victim being coached, new payee after password reset, investment advice request, vulnerable-customer cues, injection through a transaction memo, identity mismatch, unauthorised transfer request, PII in output, wrong-account disclosure. Regulated-advice rules are agent policy for testing and are never presented as legal guidance (README states it).
- **DVA variants.** Flaw rows (id, policy clause, severity, description, switch) added to the DVA registry; each pack has `permissive` and `fixed` worlds; the scripted brain exercises each flaw without a model; the live brain stays optional and uses a catalog model only.
- **ACL tester is deterministic** for a seed and needs no model; its output scenarios are written to `packs/enterprise_copilot/scenarios/generated/` only by an explicit command, never at import time.

**Steps:**
- [ ] `test_copilot_pack.py`, `test_banking_pack.py`: packs load and validate, every scenario validates, oracle good trajectories pass and bad ones fail with the expected checks, policy clause ids resolve.
- [ ] `test_acl_probes.py`: at least 40 probes for the seed world, identical output for the same seed and different for another, each probe targets a user without access, canaries are the documents' own.
- [ ] `test_copilot_dva.py`: scripted brain with the permissive handlers leaks in at least 80 percent of probes; the fixed world leaks in none (scripted brain, no model). `test_banking_dva.py`: the banking suite runs through the CLI against the DVA banking variant with the expected failures per flaw.
- [ ] Implement seed generators and handlers, scenario tables and oracles, DVA variants; **G**. Commits: `feat(packs): enterprise copilot pack and acl probes`, `feat(packs): banking pack`, `feat(dva): copilot and banking variants`.

**Done when:** both packs pass their oracle tests, the ACL tester yields at least 40 deterministic probes, the permissive copilot leaks in at least 80 percent of them and the fixed one in none, and the banking suite runs end to end through the CLI against the scripted DVA.

---

### P5-4: tau-bench retail and AgentDojo import; benchmark reproduction harness

**Batch:** r  **Depends:** P1-10, P2-2 (importer conventions), P5-3 conventions

**Scope.** Make Gauntlet's numbers comparable with published ones: import tau-bench retail and a subset of AgentDojo as packs, and provide a reproduction harness that reports the gap honestly. Nothing here is authored by us.

**Files:**
- Create: `tools/import_benchmarks/{__init__,tau_bench,agentdojo,common}.py`, `packs/taubench_retail/`, `packs/agentdojo_banking/`, `packs/agentdojo_slack/`, `benchmarks/reproduction/{__init__,__main__,harness,report}.py`, `benchmarks/reproduction/{README.md,config.yaml}`, `NOTICES` entries
- Test: `tools/import_benchmarks/tests/{test_tau_bench.py,test_agentdojo.py}`, `tests/fixtures/benchmarks/{tau_mini/,agentdojo_mini/}`, `benchmarks/reproduction/tests/test_harness.py`, `packs/*/tests/test_oracle.py`

**Interfaces:**
- Consumes: pack format, `WorldSpec`, python handler kind, `Attack` model and the attack library schema from P2-2, the runner, `pass^k` statistics (L4), `LiteLLMGateway` through the catalog.
- Produces:
  - `import_tau_bench(src: Path, out: Path, *, pin: str) -> ImportReport(tasks, portable, skipped: list[Reason])`: environment data to seed, tool functions ported to pure handlers (purity tested), each task to a `Scenario` whose `goal` is the task instruction and whose `success` is derived by replaying the task's ground-truth actions through our handlers on the initial data and emitting `state` checks per changed record plus required-output checks.
  - `import_agentdojo(src: Path, out: Path, *, suite: str, pin: str) -> ImportReport`: environment and tools to handlers, user tasks to scenarios with utility checks, injection tasks to `Attack`s with security checks; tasks not expressible in the check language are skipped with a reason and the portable percentage is printed and stored in `pack.yaml` (`import: {pin, licence, portable_pct}`).
  - `uv run python -m benchmarks.reproduction run --suite taubench_retail --model <catalog id> --trials 4 [--smoke] [--cassette-dir]` writing `benchmarks/reproduction/results/<suite>-<model>.json` (pass^k per k with intervals, per-task outcomes, deviations list) and `report` rendering the comparison table with published numbers kept in `config.yaml` (value, source, date).

**Decisions:**
- **Licences are verify items.** Check the licence and dataset terms of tau-bench and AgentDojo from their repositories (both believed MIT) before vendoring; record repo, commit, licence and date in `NOTICES` and each pack's `pack.yaml`. If a licence forbids redistribution, the importer fetches at the user's request into `.cache/` and nothing is committed (CQ-P5).
- **Pinned upstream, no authored content.** Importers refuse to run without `--pin` equal to the recorded commit (override flag, documented, prints a warning).
- **Porting is reviewed.** Every ported handler has a purity test (`assert_pure`) and, where upstream recorded results exist, a golden test; the lead reviews tool semantics. The agent under test sees the same tool names and descriptions as upstream.
- **Reproduction compares like with like.** Same model family as the published number if a cheap catalog model exists; otherwise the table states that the published number used a model we do not run (the OpenAI and Anthropic models of the papers are not run) and the comparison is shown only as context, never as a pass or fail. Acceptance for a comparable pair: within 10 points absolute on baseline utility, with a written explanation when outside. Every deviation (user simulator model, prompt, turn limits, tool formatting) is listed in the result file.
- **Cost control.** Live runs are manual, capped by `GAUNTLET_LIVE_BUDGET_USD` with the run ledger; the harness refuses without a cap. CI runs only the smoke subset from committed cassettes.

**Steps:**
- [ ] `test_tau_bench.py`, `test_agentdojo.py` on miniature upstream-format fixtures: valid worlds, scenarios and attacks; skipped tasks reported with reasons; portable percentage printed; refuses without the pin.
- [ ] `test_oracle.py` per pack: for 10 sampled tasks, replaying the ground-truth actions makes `success` hold and a perturbed action list makes it fail.
- [ ] Handler tests: purity and golden results on the fixtures.
- [ ] `test_harness.py`: smoke subset runs from cassettes in CI, result file schema valid, intervals present, deviations listed, refuses without a budget cap, no network.
- [ ] Implement; **G**. Commits: `feat(tools): tau-bench and agentdojo importers`, `feat(benchmarks): reproduction harness`. The first live reproduction run is a separate manual task with the lead's go.

**Done when:** importer and oracle tests pass on the fixtures, the portable-task percentages are recorded, and the harness reproduces its smoke subset from cassettes in CI with a valid result file.

---

### P5-5: Meta-evaluation studies and benchmark page data

**Batch:** s  **Depends:** P2-9 (DVA recall script), P3-5, P3-3 (calibration), P5-4, L-R3 (hand-labelled set)

**Scope.** Prove the platform itself works (spec section 15) with scripted, reproducible studies whose numbers are published whether or not they flatter the product. Out of scope: marketing copy and the benchmarks web page (P5-6).

**Files:**
- Create: `studies/{__init__,common,dva_recall,judge_agreement,reproducibility,cost_per_1000,simulator_fidelity,head_to_head,render,freshness}.py`, `studies/README.md` (pre-registered metrics, seeds, caveats), `benchmarks/results/*.json` (committed outputs), `docs/benchmarks/index.md` (generated), `packages/server/src/gauntlet_server/routes/meta.py`, `packages/server/src/gauntlet_server/services/meta.py`
- Test: `studies/tests/{test_results_schema.py,test_smoke_studies.py,test_render.py,test_freshness.py}`, `packages/server/tests/api/test_meta_routes.py`

**Interfaces:**
- Consumes: P2-9 DVA harness and control, P3-3 calibration and the hand-labelled set, `pass^k` and interval functions (L4), run ledgers, cassettes, scripted brains.
- Produces:
  - `StudyResult(name, version, seed, platform_version, started_at, metrics: dict[str, float], intervals: dict[str, tuple[float, float]], n: int, limitations: list[str], notes: str)` in `studies/common.py`; each study is `uv run python -m studies.<name> --seed N [--smoke] --out benchmarks/results/<name>.json`.
  - `uv run python -m studies.render` writes `docs/benchmarks/index.md` deterministically (sorted, no timestamps other than those in the data); `uv run python -m studies.freshness --release <version>` exits 1 when any result file's `platform_version` is older than the release.
  - `GET /v1/meta/benchmarks` (public, unauthenticated, read-only, `response_model=BenchmarksOut`): the committed result files as JSON for the web page, cached.

**Decisions:**
- **Metrics fixed before running** and written in `studies/README.md` with seeds: DVA recall and clean-control false positives (P2-9 script, all three DVA agents, bootstrap intervals over attack samples; control must file 0 findings); judge agreement per calibrated rubric on the L-R3 set (accuracy, fail-class precision and recall, Cohen's kappa with interval, cascade cost per verdict and escalation rate); reproducibility (one suite, one agent, 5 reruns: variance of pass rate with interval, and strict cassette replay identical for every episode); cost per 1,000 episodes from real run ledgers; simulator fidelity (guard rule hit rate and persona-guard rubric pass rate); optional head-to-head with other open-source scanners on the DVA with pinned versions, same time and cost budget, findings counted by flaw id, licences respected.
- **Models.** Only catalog models (cheap, non-OpenAI, non-Anthropic) in live runs; smoke configurations use cassettes or scripted brains so CI needs no model. Live full runs are manual, capped, and need the lead's go.
- **Honesty rules.** Negative results are committed; each metric has a `limitations` line next to it; a miss analysis accompanies recall; nothing is rounded up; intervals, not point estimates, are rendered.
- **Freshness.** Result files carry `platform_version`; the release script refuses to publish a stale page.

**Steps:**
- [ ] `test_results_schema.py`: every committed result validates as `StudyResult`, intervals bracket their metrics, seeds and versions present.
- [ ] `test_smoke_studies.py`: each study's `--smoke` configuration runs from cassettes or scripted brains in under 5 minutes total in CI and writes a valid result; control study files 0 findings.
- [ ] `test_render.py`: golden test for the rendered page; deterministic on repeat. `test_freshness.py`: a stale file fails, a current one passes.
- [ ] `test_meta_routes.py`: route returns the files, typed, unauthenticated, no workspace data, 404-free when empty (empty list).
- [ ] Implement; **G**. Commits: `feat(studies): study framework and smoke studies`, `feat(server): public benchmarks route`. Full live study runs and the committed results are a separate manual task with the lead's go.

**Done when:** every study runs in smoke mode in CI, the renderer and freshness check pass their tests, and `GET /v1/meta/benchmarks` serves the committed results.

---

### P5-6: MCP server for the platform, docs site, public challenge arena, benchmarks page

**Batch:** t  **Depends:** P1-9, P2-5, P3-4, P4-2, P4-3, P4-4, P5-5, web foundation (Phase 2-4 web)

**Scope.** The launch surfaces, built in this order inside one task: (a) an MCP server so coding agents can drive Gauntlet, (b) a documentation site, (c) the arena backend, (d) the web pages (arena, benchmarks) with Animate UI. If the batch is too large for one agent, split after (b).

**Files:**
- (a) `packages/mcp_server/pyproject.toml`, `packages/mcp_server/src/gauntlet_mcp/{__init__,server,tools,client,caps}.py` (new uv workspace member `gauntlet-mcp`, entry point `gauntlet-mcp`), tests `packages/mcp_server/tests/{test_tools.py,test_caps.py,test_confirm.py}`
- (b) `docs/user/**`, `mkdocs.yml`, `.github/workflows/docs.yml` (build only; deploy off), `tools/docs/{cli_ref,api_ref,check_ref,quickstart_check}.py`, tests `tools/docs/tests/test_refs_current.py`
- (c) `apps/arena/{pyproject.toml,arena/{app,levels,attempts,human_user,flags,limits,scan,budget}.py}`, `packs/arena/{pack.yaml,world.yaml,levels/}`, migration `packages/server/migrations/versions/0019_arena.py` (arena tables live in the same database under their own prefix), tests `apps/arena/tests/{test_levels.py,test_flags.py,test_limits.py,test_leaderboard.py,test_human_user.py}`
- (d) `apps/web/src/app/{arena,benchmarks}/**`, Playwright specs `apps/web/e2e/{arena.spec.ts,benchmarks.spec.ts}`

**Interfaces:**
- Consumes: the REST API and its generated client types, P5-5 `GET /v1/meta/benchmarks`, the engine's `run_episode` with a custom `UserSimulator` (CQ-P4), P4 gateway (`Guard`, classifier detector, approvals, taint rules, `McpGateway` pins) for levels 3 to 5, platform kill switch (P2-4), Redis.
- Produces:
  - (a) MCP tools (stdio and streamable HTTP, API key from env or header, SDK 2.x as in `gateway/mcp`): `list_agents`, `list_runs`, `get_run_report`, `get_episode`, `list_findings`, `get_finding`, `generate_scenarios`, `create_run`, `compare_runs`, `list_policies`. `create_run` requires `budget_usd` no larger than `GAUNTLET_MCP_MAX_BUDGET_USD` (default 1.0) and `confirm=true`, otherwise returns an error naming the missing argument. No tool deletes anything, changes a policy or publishes anything. Every result is size-capped (default 20 KB, truncated with a marker) and carries ids and summaries only, never secrets or raw episode text beyond the capped excerpt.
  - (b) MkDocs Material site, `mkdocs build --strict` in CI: quickstart (5 minutes to first report), concepts (episodes, journal, check language, rubrics, findings, policies), guides (hosted, wired and black-box targets, CI gate, gateway and MCP gateway, production ingest, mining), reference generated from code (CLI from Typer, REST from the OpenAPI document, check language from JSON Schema), threat taxonomy, safety and responsible use. Generators write into `docs/user/reference/`; CI fails if regenerated output differs. A quickstart check script runs the documented commands against the DVA with the scripted brain.
  - (c) Arena service: `POST /arena/v1/handles {handle}`, `POST /arena/v1/attempts {handle, level}` (creates an attempt and a fresh world), `POST /arena/v1/attempts/{id}/messages {text}` (runs one human turn), `GET /arena/v1/attempts/{id}`, `GET /arena/v1/leaderboard?level=`, `POST /arena/v1/attempts/{id}/report`, `GET /arena/v1/levels`. Tables: `arena_handles(handle pk, created_at)`, `arena_attempts(id arn_, handle, level, status /* open, solved, failed, expired */, turns, started_at, solved_at, expires_at, canary_digest)`, `arena_events(attempt_id, seq, kind, doc)` (retention, below), `arena_solves(attempt_id pk, handle, level, turns, seconds)`. `HumanUser`: a `UserSimulator` backed by an input queue; the human text is journaled as an effect of kind `human` (CQ-P4), so replay works.
  - (d) Web pages: `/arena` (level picker, chat panel, level status, leaderboard) and `/benchmarks` (renders `GET /v1/meta/benchmarks` with intervals and limitations), using Animate UI components only.

**Decisions:**
- **MCP server** wraps the REST API through a typed client with the caller's key; it never holds credentials of its own beyond that key; read tools are the default and the only write is the confirmed, capped `create_run`.
- **Docs site** is offline-buildable, has no analytics, and its deploy workflow is disabled until the lead enables it. Examples are executable and use the DVA scripted brain; any example mentioning a model uses a catalog model id.
- **Arena design.** One defended DVA-derived support-style agent with fake secrets only, no external network, no real tools beyond the arena world. Five levels: 1 prompt only, 2 plus policy rules, 3 plus the injection classifier detector (fake classifier unless the extra is installed; the level declares which), 4 plus approvals and taint rules, 5 the full gateway with MCP pinning. The agent uses a cheap catalog model in production use; tests use a scripted brain.
- **Win condition** is deterministic: per-attempt canary `HMAC(ARENA_SECRET, attempt_id)` appearing in an agent output, or a honeytool call. Flags cannot be shared between attempts or levels. Only `canary_digest` is stored, never the canary.
- **Anti-abuse.** Per-IP and per-handle rate limits (Redis), attempt caps per handle per day, per-attempt caps on turns, message length and total tokens, a total daily dollar budget with automatic closure, outputs scanned (P1-4 detectors) before returning, a report button that flags an attempt and stores nothing beyond ids, the platform kill switch closes the arena, and a global `ARENA_ENABLED=false` default. Handles are validated (charset, length, blocklist); no accounts, no emails, no IP stored beyond hashed rate-limit keys.
- **Privacy.** Attempt message text is retained `ARENA_RETENTION_DAYS` (default 14) and swept by a worker task; the leaderboard shows handle, level, turns, time only.
- **Web.** Animate UI primitives and effects only; accessibility and reduced-motion respected per the component notes; screens follow the web foundation's layout. No third-party chat widget.

**Steps:**
- [ ] (a) `test_tools.py`: in-memory MCP transport against a fake API: tool list, a read flow, workspace respected. `test_confirm.py`: `create_run` refused without `confirm` and over the cap, accepted otherwise. `test_caps.py`: size cap with marker, no secret fields pass through.
- [ ] (b) `test_refs_current.py`: generated references equal committed ones; `mkdocs build --strict` passes; the quickstart check runs green on the scripted DVA.
- [ ] (c) `test_levels.py`: a scripted solver beats level 1 and fails level 5 deterministically (cassette). `test_flags.py`: a flag from one attempt does not solve another. `test_limits.py`: rate limits, attempt caps and the daily budget close the arena and the kill switch closes it. `test_human_user.py`: human turns journaled as `human` effects and replay identical. `test_leaderboard.py`: order by turns then time, handle validation, retention sweep.
- [ ] (d) Playwright smoke: `/arena` plays a scripted attempt with a stubbed API, `/benchmarks` renders intervals and limitations; web gate passes.
- [ ] Implement; **G**, web gate. Commits: `feat(mcp): gauntlet mcp server`, `docs: user docs site and reference generators`, `feat(arena): arena service and levels`, `feat(web): arena and benchmarks pages`.

**Done when:** an MCP client lists runs and refuses an unconfirmed `create_run`, `mkdocs build --strict` and the quickstart check pass, a scripted solver deterministically beats level 1 and fails level 5 in the arena, and both web pages pass their smoke specs.

---

### P5-7: SLOs, schedules, alerts, change impact, readiness review, evidence pack

**Batch:** s  **Depends:** P3-2, P3-8, P2-6, P4-5, P5-1, P3-5 (jobs), P2-4 (audit)

**Scope.** The operations layer around releases: service-level objectives with error budgets, scheduled runs, alerts, selective re-testing on change, a go or no-go review, and an exportable evidence pack.

**Files:**
- Create: `packages/core/src/gauntlet_core/impact.py`, `packages/core/src/gauntlet_core/slo.py`, `packages/server/src/gauntlet_server/services/{slo,schedules,alerts,impact,readiness,evidence}.py`, `packages/server/src/gauntlet_server/routes/{slo,schedules,alerts,impact,readiness,evidence}.py`, `packages/cli/src/gauntlet_cli/commands/{impact,evidence}.py`, migrations `0017_ops.py` (`schedules`, `slos`, `alert_rules`, `alerts`) and `0018_evidence.py` (`evidence_packs`)
- Modify: `packages/server/src/gauntlet_server/{app,config,worker}.py` (routes, settings, scheduler tick, alert delivery job), `packages/cli/src/gauntlet_cli/main.py`, `.github/actions/gauntlet/**` (optional `impact: true` input; only if the action directory exists)
- Test: `packages/core/tests/{test_slo.py,test_impact.py}`, `packages/server/tests/ops/{test_slo_routes.py,test_schedules.py,test_alerts.py,test_impact_routes.py,test_readiness.py,test_evidence_pack.py}`, `packages/cli/tests/{test_impact_cmd.py,test_evidence_cmd.py}`

**Interfaces:**
- Consumes: stored runs and reports, the statistics module (L4: intervals, `pass^k`), `RunCreate` and `create_run`, the budget ledger, P5-1 production stats, P4 policies and gateway decisions, P4-5 `blast_radius`, P3-3 calibrations, the audit hash chain, object storage (`objectstore`), `PgJobQueue`.
- Produces:
  - Tables: `schedules(id sch_, workspace_id, agent_version_id, suite_id, cron, timezone /* UTC only in v1 */, budget_usd_micros, enabled, last_fired_at, next_fire_at, created_at)`; `slos(id slo_, workspace_id, agent_id, metric, objective real, window_days, burn_alerts jsonb, enabled, created_at)`; `alert_rules(id alr_, workspace_id, slo_id nullable, kind /* burn, breach, finding, gateway_block_rate */, params jsonb, channel_ids jsonb, silence_until, created_at)`; `alert_channels(id chn_, workspace_id, kind /* webhook, slack, email */, secret_name /* the URL or SMTP credentials live in the secret store */, created_at)`; `alerts(id alt_, workspace_id, rule_id, fingerprint, state /* firing, resolved */, payload jsonb, first_at, last_at, notified_at)` unique `(rule_id, fingerprint)`; `evidence_packs(id evp_, workspace_id, agent_version_id, frameworks jsonb, status, object_key, sha256, signed bool, created_at, finished_at)`.
  - Core: `slo_status(samples, objective, window, now) -> SloStatus(compliance, error_budget_remaining, burn_rates: dict[str, float], breached: bool, interval)` (interval-based: a breach needs the interval to exclude the objective); `compute_impact(change: Change, history: ImpactHistory) -> ImpactSet(scenario_ids, reasons: dict[str, list[str]], full_run: bool)`.
  - Routes: `POST/GET/PATCH/DELETE /v1/slos`, `GET /v1/slos/{id}/status`; `POST/GET/PATCH/DELETE /v1/schedules`, `POST /v1/schedules/{id}/run-now`; `POST/GET/PATCH /v1/alert-channels`, `POST/GET/PATCH /v1/alert-rules`, `GET /v1/alerts?state=`, `POST /v1/alerts/{id}/silence {until}`; `POST /v1/impact {from_version, to_version, policy_from?, policy_to?}` returning the impact set and a suggested suite; `GET /v1/agents/{id}/versions/{vid}/readiness?baseline=` ; `POST /v1/evidence-packs {agent_version_id, frameworks}` (job), `GET /v1/evidence-packs`, `GET /v1/evidence-packs/{id}`, `GET /v1/evidence-packs/{id}/download` (streams the zip).
  - CLI: `gauntlet impact --from VERSION --to VERSION [--json]` (exit 0), `gauntlet evidence create --agent-version ID [--framework owasp-llm]... -o pack.zip` (calls the job and downloads), `gauntlet evidence verify pack.zip` (offline: checksums, audit chain excerpt, signature if a public key is given).

**Decisions:**
- **SLO metrics:** `pass_rate` (scheduled suite), `attack_success_rate` (scheduled security suite), `latency_p95`, `cost_per_episode`, `prod_failure_rate` (P5-1 production signals). Compliance comes from the stored runs in the window; a breach needs the interval to exclude the objective, a warning needs only the point estimate; multi-window burn rates (1h, 6h, 3d windows) follow the usual fast and slow burn alert pairs.
- **Schedules** use a minimal five-field cron in UTC, evaluated by the worker tick with an injectable clock; each fire creates a run through the normal run service with the schedule's budget, claims `next_fire_at` with a compare-and-set so a tick runs once even with several workers, and skips (recording `skipped_budget`) when the workspace budget or a schedule cap would be exceeded. No schedule exists by default.
- **Alerts** deliver through the job queue: webhook (HMAC-signed body), Slack incoming webhook, SMTP email optional; URLs and credentials come from the secret store and never appear in rows, logs or responses; fingerprint de-duplication, silence windows, a resolve notification, retries with backoff, and nothing is sent unless a channel is configured (offline default).
- **Change impact** is conservative and explains itself: tool change selects scenarios whose success or forbidden checks or past tool calls reference the tool; policy change selects scenarios tagged with the changed clause and pinned regressions; model or prompt change selects a risk-stratified sample plus every pinned regression and every scenario that flipped in the last 5 runs; a world change selects scenarios using the world; a `full_run` flag is always available and is set when the change class is unknown.
- **Readiness** composes success rate, reliability (`pass^k`), safety (attack success and open findings by severity), cost and latency, each with its interval, against thresholds from a risk tier derived from tool risk (blast radius) and data access; thresholds are configuration with documented defaults; the decision is go, conditional or no-go with blockers and unverified claims (criteria without enough samples) listed, each with its evidence.
- **Evidence pack** zip contents: `manifest.json`, `RunManifest`s and run reports, posture report, coverage mapped to OWASP LLM and agentic ids (NIST AI RMF text may be quoted, ISO/IEC text never: clause numbers and our own wording only, CQ-P5), calibration results, policy versions and gateway decision summaries, audit-log excerpt with the hash-chain verification output, cassette references, `SHA256SUMS`, optional Ed25519 `SIGNATURE` (server private key from env, public key published in the manifest). Wording says "evidence supporting", never "compliant". A redaction pass and a detector scan (P1-4 secrets and PII, plus the safety rules for dangerous payloads) run before zipping; a hit fails the job.
- **Budgets.** Everything that can start runs (schedules, run-now) goes through `create_run` and the budget ledger; alert delivery and evidence packs cost no model calls.

**Steps:**
- [ ] `test_slo.py`: error budget and burn-rate tables for known inputs; breach needs the interval to exclude the objective; empty windows give `unknown`.
- [ ] `test_schedules.py`: five-field cron table, a tick fires a schedule exactly once (two workers racing), budget skip recorded, disabled schedules never fire, `run-now` audited.
- [ ] `test_alerts.py`: de-duplication on fingerprint, silence window, resolve, signed webhook body verified, secret never in rows or logs, no channel means no network call.
- [ ] `test_impact.py` and `test_impact_routes.py`: tool-schema change selects exactly the referencing scenarios plus pinned regressions; model change selects the stratified sample plus flipped and pinned; unknown change sets `full_run`; reasons present for every selected scenario; CLI output.
- [ ] `test_readiness.py`: decision table across risk tiers and sample sizes (conditional when samples are thin), thresholds overridable, blockers listed.
- [ ] `test_evidence_pack.py`: contents listed, checksums verify, embedded audit-chain verification passes and fails on a tampered row, a planted secret is absent (grep of the zip), signature verifies with the public key, `gauntlet evidence verify` works offline.
- [ ] Implement; **G**, integration. Commits: `feat(core): slo math and change impact`, `feat(server): schedules, slos and alerts`, `feat(server): readiness and evidence packs`, `feat(cli): impact and evidence commands`.

**Done when:** a scheduled run fires once per tick within budget, an SLO breach produces one de-duplicated signed alert to a test webhook, `gauntlet impact` selects the expected scenarios for a crafted tool change, readiness returns a justified decision, and an evidence pack verifies offline with a valid signature and no planted secret.

---

## Contract questions (Phase 5)

Resolved by the 2026-11-22 rulings: CQ-P1 to CQ-P5. Open, with proposals (the lead rules on review):

| ID | Question | Proposed answer |
|---|---|---|
| CQ-P6 | Production conversations and mined candidates are stored in dedicated tables (`prod_conversations`, `prod_events`, `mining_*`) while CQ-P2 also says evaluation produces `purpose=import` runs. Is the dual storage right? | Yes: dedicated tables hold the redacted source (retention applies); `import` runs hold only verdicts and ids, so deleting a conversation never deletes evaluation history. |
| CQ-P7 | The arena shares the platform database and Redis. Separate deployment of the arena (own database, own domain) for isolation? | Same codebase and migration chain, but a separate service with its own database URL setting; default compose runs it disabled (`ARENA_ENABLED=false`). It never reads workspace tables. |
| CQ-P8 | Arena levels 3 to 5 need the injection classifier; the classifier is an opt-in extra and no model is downloaded in tests. | The level definition names its classifier backend; tests and the default compose use `FakeClassifier`-style deterministic scoring behind the same detector, and the level page states which backend is live. |
| CQ-P9 | Cron schedules and SLO windows in v1 are UTC only; per-workspace time zones? | UTC only in v1, stored as `timezone='UTC'` so a later migration can add zones. |
| CQ-P10 | Alert delivery (webhook, Slack, SMTP) is outbound network: it conflicts with "offline defaults" unless opt-in. | Opt-in per channel; a channel stores only a secret name; with no channels configured nothing is sent. Evidence-pack signing uses a server key from env and is skipped (unsigned pack, flagged) when absent. |
| CQ-P11 | P5-6 bundles four deliverables; the batch may exceed one agent. | Allowed split after (b): batch t1 = MCP server and docs site, batch t2 = arena and web pages. The lead decides at dispatch. |
| CQ-P12 | The reproduction harness compares with published tau-bench and AgentDojo numbers that used OpenAI or Anthropic models, which this project does not run. | Compare only where a catalog model family matches; otherwise publish our model's number next to the published one as context with no pass or fail, and say so in the README and result files. |
