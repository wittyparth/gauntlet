# Phase 4 gateway and policies: P4-1 to P4-5

Batches: **n** = P4-1, P4-2, P4-3 (one agent, in order P4-2, P4-1, P4-3 is also acceptable; P4-3 needs P4-2). **o** = P4-4, P4-5. (P4-6 is web, in `phase-2-4-web.md`.) L8 (policy engine, offline policy testing, rule suggestion) is lead-owned: `PolicyEngine.decide(prefix, proposed) -> GatewayDecision(action, rule_id, message, evidence)` (hard-cores 7.1), the offline tester (7.2) and `suggest_rule(finding)` (7.3). Names below that belong to L8 or L5 (`PrefixView`, `ProposedAction`, the offline-test entry point and report type, the prefix-evaluability validator) are placeholders for what those modules export (CQ-G1); if L8 is not merged, stop and report.

Read first: `docs/plan/README.md`, `docs/plan/02-contracts.md` (sections 4, 7, 8), `docs/plan/03-hard-cores.md` sections 4 and 7, `phase-2-security.md` (findings, scanner rules MCP-001 to MCP-011, audit log), `phase-3-rigor.md` (jobs queue), and spec section 9 in `agent-testing-platform-plan.md`.

**G** (gate) = `uv run ruff check . && uv run ruff format --check . && uv run pyright packages && uv run pytest packages tests apps -q`. Latency benchmarks live under `tests/bench/` and run with `uv run pytest tests/bench -q`.

Design rule for the whole phase: the policy engine is pure and synchronous; everything that needs I/O (approvals, sinks, models) lives outside it, and every external call has a latency budget and a fail-open or fail-closed rule taken from the policy.

---

### P4-1: Policy compiler

**Batch:** n  **Depends:** L8, P1-1, P3-5 (jobs)

**Files:**
- Create: `packages/core/src/gauntlet_core/policy/compile/{__init__,clauses,propose,validate,coverage,prompts}.py`, `packages/server/src/gauntlet_server/services/policies.py`, `packages/server/src/gauntlet_server/routes/policies.py`, `packages/server/migrations/versions/0009_policies.py`, `packages/cli/src/gauntlet_cli/commands/policy.py`
- Test: `packages/core/tests/policy/compile/{test_clauses.py,test_propose.py,test_validate.py,test_coverage.py}`, `packages/server/tests/policy/{test_policy_routes.py,test_review_flow.py}`, `packages/cli/tests/test_policy_cmd.py`

**Interfaces:**
- Consumes: `Policy`, `PolicyRule`, `Rubric`, `Check` models; `Gateway` (`generator` role, structured output), `json_schema`; L8 prefix-evaluability validator and offline tester; P3-5 `JobQueue`.
- Produces:
  - `split_clauses(text: str) -> list[Clause]` (`Clause(id, text, source_span)`).
  - `Proposal` (pydantic): `clause_id, clause_text, klass: Literal["machine","model","human"], rule: PolicyRule | None, rubric: Rubric | None, confidence: float, rationale: str, status: Literal["proposed","accepted","rejected","edited"]`.
  - `compile_policy(text: str, *, tools: Sequence[ToolSpec], gateway: Gateway, policy_id: str, seed: int = 0) -> CompiledPolicy` (`proposals: list[Proposal]`, `cost: Cost`).
  - `coverage_report(compiled, offline_results | None) -> CoverageReport`.
  - Tables `policies(id pol_, workspace_id, version, doc jsonb /* Policy */, status draft|published, source_text, created_at)` unique `(id, version)`, `policy_proposals(id, policy_id, version, doc jsonb /* CompiledPolicy */, created_at)`.
  - Routes (CQ-W24 as proposals): `POST /v1/policies/compile {agent_id | text, tools_from_world_id?, name}` returns `{job_id}` (a `compile_policy` job); `GET /v1/policies`, `GET /v1/policies/{id}` (latest, with `?version=`); `GET /v1/policies/{id}/proposals`; `PATCH /v1/policies/{id}/proposals/{clause_id} {status, rule?}` (edits are validated); `POST /v1/policies/{id}/publish {mode?: "shadow"|"enforce", fail?: "open"|"closed"}` creates a new immutable version from accepted proposals (default `mode=shadow`, `fail=open`); `GET /v1/policies/{id}/coverage`. CLI: `gauntlet policy compile FILE|--agent-text -o policy.yaml`, `gauntlet policy validate policy.yaml`.

**Decisions:**
- **Three rule classes.** `machine`: expressible as a prefix-evaluable `PolicyRule` (tool allow/deny, argument constraints with `ref`, sequences such as "after reading untrusted content block outbound email", egress allowlists, canary or detector checks, tainted calls); `model`: needs a judgment (tone, "do not give legal advice"): becomes a `Rubric` for offline evaluation and shadow scoring, not an enforceable rule; `human`: needs a person (approvals, commitments outside the system): becomes a `require_approval` rule on the nearest tool if one exists, else a checklist item with no enforcement.
- **Pipeline.** (1) `split_clauses`: split on numbered or bulleted items and blank-line paragraphs; sentences stay together unless they exceed 400 characters (then split on `;` or sentence end); each clause gets an id `c01`, `c02`, ... in order; (2) one structured model call per batch of 8 clauses (`generator` role, `response_model=ProposalBatch`) with the system prompt containing: the JSON Schema of `PolicyRule` (from `json_schema`), the check vocabulary table from contracts section 4 marked "prefix-evaluable" or "not allowed in rules" (`judge`, `state_diff`), the tool names with risk and argument schema, and at least 6 few-shot clause to rule examples built from the ecommerce policy (for example "refund over 10000 cents requires escalation" to `require_approval` on `tool_called issue_refund args amount_cents gt 10000`; "only one coupon per order" to a `sequence`/count rule with `block`; "never reveal other customers' data" to a `model` rubric; "address changes only while processing" to a `block` rule with a `state` check that is `undetermined` in production, so the proposal sets `strict: false`); (3) code validates each proposed rule: schema validation, then the L8/L5 prefix-evaluability validator; a rule that fails is downgraded to `klass="model"` with a rubric drafted from the clause (a second call) or to `human` when no rubric is sensible, and the rationale records the downgrade; tool names and argument paths must exist in the tool inventory; unknown names are an error that triggers one repair call, then downgrade.
- **Defaults on proposals**: `severity` from keywords (`never`, `must not`, `prohibited` give high; `should` gives medium; unspecified medium); `action`: `block` for hard prohibitions, `require_approval` for "needs approval/escalate", `log` for soft guidance; `message` is a short agent-facing sentence the rule returns when blocking. Confidence below 0.6 is flagged in the review UI; every proposal needs an explicit `accepted` before publish (no auto-accept).
- **Offline check before accept** (optional, at coverage time): each machine rule is run through the L8 offline tester against available trajectories; a rule that blocks more than 5 percent of benign trajectories is annotated `high_false_positive_risk` with the count (annotation only).
- **Coverage report** (`GET /policies/{id}/coverage`): `{clauses_total, machine, model, human, uncovered (clauses with no accepted proposal), rules_exercised: [{rule_id, attack_hits, benign_hits}], rules_untested: [rule_id] (no trajectory evaluates it as violates-or-ok), by_clause: [{clause_id, text, klass, status, rule_id | null}]}`. "Exercised" means at least one stored trajectory evaluates the rule `violates` or `ok` (not `undetermined`).
- **Versioning**: published versions are immutable; edits create a draft with `version+1`; `mode` changes also create a version. Publishing writes an audit row (`policy.published`) with the version and the accepted rule ids.
- **Determinism and cost**: `temperature=0`, `seed` passed through; compile cost returned and shown; tests use `FakeLLM`.

**Steps:**
- [ ] `test_clauses.py`: numbered, bulleted, paragraph, over-long sentence splitting, ids stable. `test_validate.py`: a rule with a `judge` node is downgraded; unknown tool name repaired once then downgraded; valid rule survives.
- [ ] `test_propose.py` (FakeLLM scripted per batch): the six few-shot style clauses give the expected classes and rules, severities and actions follow keyword defaults, low confidence flagged, prompt contains the schema and tool inventory (assert on `fake.calls`), batch of 8.
- [ ] `test_coverage.py`: counts per class, uncovered clauses, exercised versus untested rules on hand-built trajectories, high-false-positive annotation.
- [ ] `test_policy_routes.py`, `test_review_flow.py` (integration): compile job produces proposals; accept/reject/edit (invalid edit 422); publish needs at least one accepted; immutable versions; audit rows; cross-workspace 404.
- [ ] Implement; **G** and integration. Commits: `feat(policy): policy compiler`, `feat(server): policy routes and review flow`, `feat(cli): policy compile and validate`.

**Done when:** compiling `packs/ecommerce/policy.md` against the pack's tools yields proposals for R1 to R11 with at least 5 machine rules that validate, a rubric for the tone clause, and a coverage report whose numbers add up.

---

### P4-2: Gateway as Python SDK middleware

**Batch:** n  **Depends:** L8, L5, P2-4 (audit)

**Files:**
- Create: `packages/core/src/gauntlet_core/gateway/{__init__,guard,session,wrap,sinks,approvals,decision,errors}.py`, `packages/server/src/gauntlet_server/services/gateway.py`, `packages/server/src/gauntlet_server/routes/gateway.py`, `packages/server/migrations/versions/0010_gateway.py`, `examples/gateway/{openai_tools.py,policy.yaml}`
- Test: `packages/core/tests/gateway/{test_session.py,test_wrap.py,test_modes.py,test_failopen.py,test_sinks.py,test_approvals.py}`, `tests/bench/test_guard_latency.py`, `packages/server/tests/gateway/{test_decisions_routes.py,test_approval_routes.py}`

**Interfaces:**
- Consumes: L8 `PolicyEngine`, L5 `PrefixView`/`ProposedAction` and `Event` construction, `Policy`, `GatewayDecision`, `Origin`, `redact`, `load_yaml`.
- Produces (the SDK surface, module `gauntlet_core.gateway`):
  - `Guard(policy: Policy | str | Path, *, mode: Literal["shadow","enforce"] | None = None, sink: DecisionSink | None = None, approvals: ApprovalHandler | None = None, agent_id: str | None = None, clock: Callable[[], datetime] = utcnow, log_args: Literal["full","redacted","hash"] = "redacted", approval_timeout_s: float = 300.0, on_timeout: Literal["deny","allow"] = "deny", on_block: Literal["raise","return"] = "raise")`.
  - `Guard.session(session_id: str | None = None, *, user_id: str | None = None) -> Session`.
  - `Session` (async methods): `record_user_message(text)`, `record_agent_message(text)`, `record_tool_result(call_id, tool, result, *, untrusted: bool | None = None, source: str | None = None)`, `check_tool_call(tool, args, *, call_id=None) -> GatewayDecision`, `check_output(text) -> GatewayDecision` (a `redact` decision carries the replacement text in `decision.modified`), property `events`.
  - `Guard.wrap(fn, *, tool: str | None = None, risk: str | None = None, untrusted_output: bool = False)` and decorator `@guard.tool(...)`: wraps a sync or async tool function; it needs a current session from a `contextvars` variable set by `async with session.active():` (or an explicit `session=` argument).
  - `PolicyBlocked(Exception)` carrying `decision`; `DecisionSink` Protocol (`async write(record: DecisionRecord)`), implementations `MemorySink`, `JsonlSink(path)`, `HttpSink(api_url, api_key, *, flush_interval_s=2.0, max_queue=10_000)`; `ApprovalHandler` Protocol (`async request(decision, record) -> Literal["approved","denied"]`), implementations `CallbackApprovals(fn)` and `HttpApprovals(api_url, api_key, poll_interval_s=1.0)`.
  - `DecisionRecord` (pydantic): `id, ts, session_id, agent_id, policy_id, policy_version, mode, kind: tool_call|output, tool, args (per log_args), action, enforced: bool, would_have: action | None, rule_id, severity, message, evidence, approval: {id, outcome} | None, overhead_us, guard_error: str | None`.
  - Server: tables `gateway_decisions(id, workspace_id, ts, session_id, agent_id, policy_id, policy_version, mode, kind, tool, action, enforced, rule_id, severity, overhead_us, doc jsonb)` and `gateway_approvals(id gap_, workspace_id, decision_doc jsonb, status pending|approved|denied|expired, requested_at, expires_at, decided_by, decided_at, note)`; routes `POST /v1/gateway/decisions` (batch up to 500), `GET /v1/gateway/decisions` (filters `policy_id, action, tool, rule_id, mode, from, to, enforced`; `limit/cursor`), `GET /v1/gateway/stats?window=1h` (counts by action and rule, overhead p50, p95, p99), `POST /v1/gateway/approvals`, `GET /v1/gateway/approvals?status=`, `GET /v1/gateway/approvals/{id}`, `POST /v1/gateway/approvals/{id}/decide {decision: approve|deny, note?}`. Resolves CQ-W24 as a proposal.

**Decisions:**
- **Behaviour per action** (when the mode is `enforce`; in `shadow` nothing is ever blocked, modified or held, the record carries `enforced=false` and `would_have=<action>`):

| Engine action | `check_tool_call` result | `wrap` behaviour |
|---|---|---|
| none (allow) | decision `allow` | run the tool |
| `block` | decision `block` with `message` | `on_block="raise"`: raise `PolicyBlocked`; `on_block="return"`: return `{"error": "blocked_by_policy", "message": <rule message>}` as the tool's result so the agent can recover |
| `require_approval` | the approval handler is awaited | approved runs the tool; denied is treated as `block`; timeout follows `on_timeout` (default deny, recorded as `approval.outcome="expired"`) |
| `redact` | decision `redact` | tool output text is passed through the rule's redaction (replace matches with `[REDACTED]`) before returning; for `check_output` the replacement is `decision.modified` |
| `log` | decision `allow`, `action="log"` | run the tool, record |

- **Session and prefix.** The session keeps a list of `Event`s (assigned dense seqs, `sim_time` = `clock()` since this runs in production, not the engine's simulated clock) with origins: user messages `Origin(trust="user")`; tool results `untrusted_external` when `untrusted=True`, or when the tool name matches `Guard(..., origin_rules)` (glob list, see P4-4), else `system`; agent messages `system`. `check_tool_call` appends a `tool_call` event to the prefix **after** the decision (so rules see history plus the proposed call, as the engine expects) and appends the `tool_result` when `record_tool_result` is called. The prefix is capped at 500 events (oldest dropped, with the first `user_message` and any `untrusted` markers retained).
- **Fail-open or fail-closed.** Any exception inside the guard's evaluation (engine bug, malformed policy at call time) is caught: `policy.fail == "open"` gives an `allow` decision with `guard_error` set and a warning log; `"closed"` gives `block` with `message="policy engine unavailable"`. Sink and approval-transport errors never raise into the agent: sink errors are logged and counted (`sink_errors` metric on the guard), approval transport errors follow `on_timeout`.
- **Latency budget.** `overhead_us` measures from `check_tool_call` entry to return (excluding approval waiting). `tests/bench/test_guard_latency.py` asserts, with a 50-rule policy and a 200-event prefix, p99 below 5 ms for `check_tool_call` end to end (the engine alone is below 2 ms per hard-cores 7.1), over 5,000 iterations on CI hardware with a generous 3x margin on shared runners (use `GAUNTLET_BENCH_FACTOR`).
- **Argument logging.** `log_args="redacted"` (default) runs `redact` and truncates to 2 KB; `"hash"` stores only `sha256` of canonical args; `"full"` stores args as given (documented as unsafe for secrets). Results are never logged.
- **HttpSink**: in-memory bounded queue (10,000, drop oldest and count drops), batches of up to 500 posted to `POST /v1/gateway/decisions` every `flush_interval_s` or when 200 records are queued, retries with exponential backoff (cap 30 s) on 5xx and connection errors, `aclose()` flushes. It never blocks `check_tool_call`. `JsonlSink` appends one JSON per line with an `asyncio.Lock`.
- **Approvals over HTTP**: `HttpApprovals.request` posts `POST /v1/gateway/approvals` (decision plus the exact action: tool, args per `log_args`, rule, message, session id, expiry = now + `approval_timeout_s`), then polls `GET /v1/gateway/approvals/{id}` every second until `approved`, `denied` or `expired`; the server marks pending approvals `expired` when `expires_at` passes (lazy on read plus a worker sweep every 30 s). `decide` is idempotent and writes an audit row.
- **Policy loading**: a `str` or `Path` is a YAML file loaded with `load_yaml(Policy, ...)`; load fails fast if any rule's `when` is not prefix-evaluable (L8 validator). `Guard.reload(policy)` swaps the policy atomically (sessions see the new policy on their next call). `mode` argument overrides the policy's own mode.
- **Not in this task**: framework adapters (LangChain, OpenAI Agents SDK, and the rest are deferred), the reverse-proxy form, the MCP proxy (P4-3), the injection classifier (P4-4).
- **Example** `examples/gateway/openai_tools.py` (about 40 lines): a minimal tool loop with the OpenAI-style client stubbed, two guarded tools, shadow then enforce, runnable offline; it is exercised by a test so it cannot rot.

**Steps:**
- [ ] `test_session.py`: origin tagging (untrusted flag, glob rules), prefix ordering (tool_call appended after decision), cap behaviour, seqs dense. `test_modes.py`: shadow never blocks and records `would_have`; enforce blocks; mode override. `test_wrap.py`: sync and async tools, `raise` vs `return`, context-var session, redact on output, `log` action runs the tool.
- [ ] `test_failopen.py`: engine raising under `fail=open` allows with `guard_error`; `closed` blocks; sink down does not raise; approval transport down follows `on_timeout`.
- [ ] `test_approvals.py` (fake HTTP via respx or in-process ASGI): approve, deny, timeout deny, timeout allow, expiry sweep; `test_sinks.py`: batching, backoff, drop-oldest accounting, `aclose` flush, jsonl format.
- [ ] `tests/bench/test_guard_latency.py` as specified. `test_decisions_routes.py`, `test_approval_routes.py` (integration): batch ingest, filters, stats percentiles on known overheads, decide idempotent, expired cannot be decided (409), scoping.
- [ ] Implement; **G**, bench, integration. Commits: `feat(gateway): sdk guard, session, wrap`, `feat(gateway): sinks and approvals`, `feat(server): gateway decision and approval routes`.

**Done when:** the example script blocks a refund over the limit in enforce mode, merely logs it in shadow mode (with `would_have`), the decision shows up in `GET /v1/gateway/decisions`, an approval created by `require_approval` can be decided over HTTP, and the latency benchmark passes.

---

### P4-3: MCP gateway

**Batch:** n  **Depends:** P4-2, P2-8

**Files:**
- Create: `packages/core/src/gauntlet_core/gateway/mcp/{__init__,config,pins,proxy,namespace,scan_hook}.py`, `packages/cli/src/gauntlet_cli/commands/mcp_gateway.py`, `examples/gateway/mcp-gateway.yaml`
- Modify: `packages/core/src/gauntlet_core/security/scan/mcp_rules.py` (add `MCP-012`), `packages/cli/pyproject.toml` and `packages/core/pyproject.toml` (`mcp>=1.0` as an optional extra `mcp` on core; verify the SDK's server and client APIs for the proxy)
- Test: `packages/core/tests/gateway/mcp/{test_pins.py,test_namespace.py,test_proxy.py,test_scan_hook.py,test_config.py}`, `packages/cli/tests/test_mcp_gateway_cmd.py`

**Interfaces:**
- Consumes: P4-2 `Guard`/`Session` and approvals, P2-8 `scan_mcp_tools` and rules, the `mcp` SDK (stdio and streamable HTTP client and server), `Policy`.
- Produces:
  - `McpGatewayConfig` (pydantic) loaded from YAML (below); `PinStore` (`load(path)`, `save`, `check(server, tool_listing) -> PinReport`, `approve(server, tools)`).
  - `tool_pin_hash(tool: dict) -> str` (the recipe below) and `server_manifest_hash(tool_hashes: Mapping[str, str]) -> str`.
  - `McpGateway(config, guard: Guard | None)` with `async serve_stdio()` and `async serve_http(host, port)`; it exposes one MCP server to the agent client and proxies to the configured upstream servers.
  - Rule `MCP-012` (pin mismatch, severity critical) in the scanner's rule set, used when a pin file is supplied: `gauntlet scan mcp ... --pins pins.json`.
  - CLI: `gauntlet mcp-gateway serve --config gateway.yaml [--http HOST:PORT]`, `gauntlet mcp pin --config gateway.yaml [--approve-all | --tool server/tool ...] [--pins pins.json]`, `gauntlet mcp diff --config gateway.yaml [--pins pins.json]`.

**Decisions:**
- **Config** (`gateway.yaml`):
  ```yaml
  policy: policy.yaml            # optional; same Policy as the SDK
  pins: pins.json
  on_pin_mismatch: block         # block | warn
  on_unpinned: block             # block | warn   (a tool never approved)
  scan:
    block_at: high               # description scan findings at or above this hide the tool
  servers:
    - name: files                # namespace prefix, ^[a-z][a-z0-9_]{0,30}$
      transport: stdio           # stdio | http
      command: ["npx", "some-mcp-server"]   # stdio
      env: {ROOT_DIR: /srv/data}            # only these env vars reach the server (credential isolation)
      trust: untrusted           # trusted | untrusted (origin of its tool results)
      allow_tools: ["read_*"]    # glob; empty or missing means allow all
      deny_tools: ["delete_*"]
      scopes: {max_risk: write}  # read | write | destructive | financial | external_comm; tools above are hidden
    - name: crm
      transport: http
      url: https://crm.example.test/mcp
      headers: {Authorization: "${CRM_TOKEN}"}  # ${ENV} interpolated; never written to logs or decisions
      trust: untrusted
  ```
  Unknown keys are rejected. Header and env values are interpolated from the gateway's environment only for the named keys.
- **Namespace isolation.** Tools are exposed to the agent as `<server>__<tool>` (double underscore); the original name never appears alone, so two servers cannot shadow each other. The exposed description is prefixed `[server: <name>] `. `tools/call` for a name without a known namespace prefix is an error `-32602`. A listing in which a server's tool name already contains `__` is renamed `<server>__<tool with __ replaced by _>` and a warning is logged.
- **Pinning hash recipe** (exact; this is the rug-pull defence). For each upstream tool take the object `{"name", "title", "description", "inputSchema", "outputSchema", "annotations"}` using exactly the keys the server returned (a missing key is omitted, not `null`); `description` and `title` are not normalised except for Unicode NFC. Serialise with `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, encode UTF-8, and `hash = "sha256:" + sha256(bytes).hexdigest()`. Invisible characters are deliberately kept, so adding a zero-width character changes the hash. `server_manifest_hash` is `sha256` of the lines `"<tool name>\t<tool hash>\n"` sorted by tool name. `pins.json`: `{"version": 1, "servers": {"<name>": {"manifest": "sha256:...", "server_info": {"name": ..., "version": ...}, "approved_at": ISO8601, "approved_by": str, "tools": {"<tool>": {"hash": "sha256:...", "approved_at": ...}}}}}`; `server_info` is recorded but not part of any hash (version bumps alone do not alarm).
- **Behaviour on change.** At gateway start and on every upstream `notifications/tools/list_changed` and every `tools/list`: recompute hashes. Mismatch for a pinned tool: with `on_pin_mismatch: block` the tool is hidden from `tools/list`, calls return an error, the gateway emits `notifications/tools/list_changed` to the client, and a decision record with `rule_id="mcp.pin_mismatch"`, severity critical is written; with `warn` the tool stays visible and the record is written. A tool absent from the pins: `on_unpinned` likewise (`mcp.unpinned`, severity medium). A pinned tool that disappears is logged (`mcp.pin_removed`, low). `gauntlet mcp diff` prints per tool `unchanged | changed | new | removed` with a unified diff of the canonical JSON for changed ones.
- **Description scanning.** Every upstream tool listing goes through P2-8's rules MCP-001 to MCP-008 and MCP-011 before exposure; findings at or above `scan.block_at` hide the tool (record `mcp.scan_blocked` with the rule ids). Scanning results are cached per tool hash.
- **Call interception.** Every `tools/call` goes through the P4-2 `Guard` session for the MCP session (one gateway session per client connection): origin of the result is `untrusted_external` when the server's `trust` is `untrusted` (the default) so taint-style rules (`sequence`: after reading external content, block outbound email) work without markers; the tool risk used in policy `risk` matchers comes from `scopes.max_risk` mapping or the annotation hints (`readOnlyHint` gives `read`, `destructiveHint` gives `destructive`, else `write`), overridable per tool in the config (`risk_overrides: {"files__write_file": destructive}`). `require_approval` uses the Guard's `ApprovalHandler`. Allow and deny globs are applied first and a denied tool behaves as absent.
- **Credential isolation**: stdio servers are spawned with only the configured `env`, plus `PATH`; the agent client's own credentials never reach upstreams, and upstream credentials never appear in tool listings or logs (decision args pass through `redact`).
- **Scope of this task**: the proxy, pinning, allowlists, namespacing, scanning hook and interception. Streaming progress notifications and resource or prompt proxying are pass-through only (not policy-checked) and documented as such.

**Steps:**
- [ ] `test_pins.py`: hash recipe against 3 fixed fixture tools with the expected digests written into the test (so an accidental change in canonicalisation fails), zero-width character changes the hash, key order independent, missing key omitted vs null differ, manifest hash order independence, `check` reports changed/new/removed, `approve` writes `pins.json` round trip.
- [ ] `test_namespace.py`: prefixing, collision with `__`, unknown prefix error, description prefix. `test_config.py`: valid, unknown key rejected, env interpolation, bad server name.
- [ ] `test_scan_hook.py`: a poisoned fixture tool (from P2-8 fixtures) is hidden and recorded; clean tools pass; cache hit.
- [ ] `test_proxy.py` with in-process fake upstream MCP servers (the `mcp` SDK's in-memory transport): `tools/list` merges and namespaces; allow and deny globs; `max_risk` hides tools; a call goes through the guard (block rule blocks, shadow mode passes and records); `require_approval` flow; rug pull: upstream changes a description after pinning, the tool disappears and `list_changed` is emitted; unpinned tool blocked; env isolation (the fake upstream asserts the env it received); header interpolation not logged.
- [ ] `test_mcp_gateway_cmd.py`: `pin --approve-all` writes pins, `diff` output, `serve` smoke via stdio against fake upstreams.
- [ ] Implement; **G**. Commits: `feat(gateway): mcp pinning and namespacing`, `feat(gateway): mcp proxy with policy interception`.

**Done when:** an agent client connected through `gauntlet mcp-gateway serve` sees namespaced tools, a description changed upstream after approval makes that tool vanish with a critical decision record, and a `block` rule stops a destructive call in enforce mode.

---

### P4-4: Injection classifier detector and origin tagging

**Batch:** o  **Depends:** P4-2, P2-2 (evaluation corpus)

**Files:**
- Create: `packages/core/src/gauntlet_core/gateway/classifier/{__init__,model,detector,origin,eval}.py`, `tools/export_classifier.py`, `tests/fixtures/classifier_eval/{README.md,build.py}`
- Modify: `packages/core/pyproject.toml` (optional extra `classifier`: `onnxruntime`, `tokenizers`, `numpy`; fallback extra `classifier-torch`: `transformers`, `torch`), `packages/core/src/gauntlet_core/gateway/guard.py` (origin rules hook)
- Test: `packages/core/tests/gateway/classifier/{test_detector.py,test_origin.py,test_model_fake.py,test_chunking.py}`, `packages/core/tests/gateway/classifier/test_model_real.py` (skipped unless `GAUNTLET_CLASSIFIER_TEST=1`), `tests/bench/test_classifier_latency.py` (same switch)

**Interfaces:**
- Consumes: L5 detector registry (the `Detector` node; same registration as P1-4), P4-2 `Session`/`Guard`, `Origin`, the attack library (positives) and pack documents (negatives).
- Produces:
  - `InjectionClassifier` Protocol (`score(texts: Sequence[str]) -> list[float]`, probability that the text is an injection) with `OnnxClassifier(model_dir)`, `TorchClassifier(model_name)`, and `FakeClassifier(fn)` for tests.
  - Detector name `injection_classifier` with params `{threshold: 0.9, scope: "untrusted" | "all" = "untrusted", max_tokens: 512, stride: 256, latency_budget_ms: 50}`.
  - `OriginRules` (`Guard(origin_rules=[...])`): list of `{tool: glob, trust: "system"|"user"|"untrusted_external"}`, first match wins, default from `wrap(untrusted_output=...)` else `system`; `Guard.origin_defaults` ships with conservative globs (`*fetch*`, `*browse*`, `*search*`, `*read_email*`, `*inbox*`, `*web*`, `*scrape*`, `*download*` as untrusted).
  - `evaluate_classifier(classifier, positives, negatives) -> {tpr_at_fpr_1pct, auc, threshold_at_fpr_1pct, n_pos, n_neg}` and the corpus builder.

**Decisions:**
- **Model choice (verify before shipping).** Default open-source local model: `protectai/deberta-v3-base-prompt-injection-v2` (a DeBERTa-v3-base binary classifier; Apache-2.0 per its card, **verify licence and current availability**). Alternatives to evaluate and record in a comment in `model.py`: Meta Prompt Guard 2 (Llama-licensed and gated, **verify terms**), `deepset/deberta-v3-base-injection` (**verify licence**). The model id and revision hash are config (`GAUNTLET_CLASSIFIER_MODEL`, `GAUNTLET_CLASSIFIER_REVISION`), never hardcoded in logic; the default revision is pinned to a commit hash looked up at build time.
- **Runtime.** CPU ONNX is the primary path: `tools/export_classifier.py` exports the model once with `optimum`/`transformers` to `~/.cache/gauntlet/classifier/<revision>/model.onnx` plus tokenizer files (a documented one-time offline step; the runtime never downloads at call time unless `GAUNTLET_CLASSIFIER_AUTO_EXPORT=true`). `OnnxClassifier` uses `onnxruntime` (`CPUExecutionProvider`, intra-op threads 2) and the `tokenizers` package; the torch path is a fallback behind the `classifier-torch` extra. The model is loaded at `Guard` construction when the policy uses the detector (warm start), not on first call.
- **Detector semantics** (prefix-evaluable): scans `tool_result` events with `Origin.trust == "untrusted_external"` (or all tool results when `scope="all"`, plus the proposed output for output checks) that have not been scanned in this session (cache by `sha256` of text, per session and global LRU of 10,000). Texts longer than `max_tokens` are split into windows of `max_tokens` tokens with `stride` overlap; the score is the max over windows. `score >= threshold` makes the check hold (the rule's `when` fires). If the scan would exceed `latency_budget_ms` (measured with a monotonic clock; windows are scored in batches and the loop stops at the budget) the result is `undetermined`, which follows the policy's `fail` setting only for `strict` rules (hard-cores 7.1). Evidence is the `seq` of the flagged event and the highest-scoring window truncated to 200 characters.
- **Origin tagging** lives in the SDK `Session` (P4-2) and is configured by `origin_rules`; `Guard.wrap(untrusted_output=True)` and the MCP gateway's `trust: untrusted` feed the same field. Taint markers are test-only; production uses origin trust plus `sequence` rules ("after untrusted content was read, block outbound email") and this classifier.
- **Evaluation corpus** (`tests/fixtures/classifier_eval/build.py`, deterministic, seeded): positives are library attacks with `vector` in `tool_result` or `document` (payload with placeholders substituted by fixed fake values, benign surrounding document text taken from pack documents), at most 300; negatives are benign texts from the ecommerce and hall-of-failures packs (document bodies, tool-result JSON, order notes) plus 200 neutral paragraphs generated by a seeded template over the world data; no authored attack text. The real-model test asserts a measured TPR at 1 percent FPR and prints it; the threshold for the assertion is set from the first measured value minus a margin and recorded in the test.
- **Latency target**: p95 below 30 ms per 512-token window on a modern laptop CPU with ONNX (benchmark test behind the switch records the number; failing the target produces a report, not a CI failure, because hardware varies).

**Steps:**
- [ ] `test_model_fake.py`/`test_detector.py` (with `FakeClassifier`): only untrusted-origin results scanned by default, `scope="all"` scans all, threshold boundary, cache prevents rescans, evidence quote, `undetermined` on exceeding the latency budget (fake slow classifier and injected clock), strict versus non-strict rule behaviour through `PolicyEngine`.
- [ ] `test_chunking.py`: window boundaries and stride on token counts, max over windows, empty text. `test_origin.py`: glob first-match, default untrusted globs, `wrap(untrusted_output=True)` overrides, MCP `trust` propagation.
- [ ] `test_model_real.py` and `tests/bench/test_classifier_latency.py` (skipped by default): export once, evaluate on the corpus, print TPR@1%FPR and p95.
- [ ] Implement; export script; **G**. Commits: `feat(gateway): injection classifier detector`, `feat(gateway): origin rules`.

**Done when:** a policy with `detector injection_classifier` blocks a tool call that follows an untrusted tool result containing an injected instruction (with the real model when `GAUNTLET_CLASSIFIER_TEST=1`, with the fake otherwise), and the measured TPR at 1 percent FPR and p95 latency are recorded in the body of the final commit message (no results file is committed).

---

### P4-5: Closed loop wiring, blast radius and permission diff

**Batch:** o  **Depends:** L8, P2-5, P4-1, P4-2

**Files:**
- Create: `packages/core/src/gauntlet_core/gateway/guarded_world.py`, `packages/core/src/gauntlet_core/policy/blast.py`, `packages/server/src/gauntlet_server/services/{loop,blast}.py`, `packages/server/src/gauntlet_server/routes/{loop,blast}.py`, `packages/server/migrations/versions/0011_policy_tests.py`
- Modify: `packages/core/src/gauntlet_core/runner.py` (`EpisodeJob.policy`, wrap the world with `GuardedWorld` when set), `packages/server/src/gauntlet_server/services/runs.py` (run `policy_id`/`policy_version` column), `packages/server/src/gauntlet_server/worker.py` (job kinds `policy_test`, `verify_with_policy`)
- Test: `packages/core/tests/gateway/test_guarded_world.py`, `packages/core/tests/policy/test_blast.py`, `packages/server/tests/policy/{test_loop_routes.py,test_policy_tests_job.py,test_verify_with_policy.py,test_blast_routes.py}`, `tests/integration/test_closed_loop.py`

**Interfaces:**
- Consumes: L8 `suggest_rule`, offline tester and its report (CQ-G1), P2-5 findings (`reproducer`, `suggested_policy`, episodes, `verify`), P4-1 policies, P4-2 `Guard`, P3-5 jobs, `World`, `ToolSpec`.
- Produces:
  - `GuardedWorld(world: World, session: Session)`: same interface as `World` (`call_tool`, `snapshot`, `tool_schemas`) that consults the guard first.
  - `blast_radius(tools: Sequence[ToolSpec], observed: ObservedEffects, policy: Policy | None) -> BlastRadius`; `permission_diff(old: Sequence[ToolSpec], new: Sequence[ToolSpec], policy: Policy | None) -> PermissionDiff`.
  - Tables `policy_tests(id ptest_, workspace_id, policy_id, policy_version, agent_version_id, status, result jsonb, attack_count, benign_count, created_at, finished_at)`; runs gain `policy_id` and `policy_version` (nullable; CQ-G3).
  - Routes (CQ-W24 as proposals): `POST /v1/findings/{id}/suggest-policy` (job; returns `{job_id}`), `POST /v1/policies/{id}/test {agent_version_id, attack_runs?: [run_id], benign_runs?: [run_id], max_benign?: 200}` (job), `GET /v1/policies/{id}/tests`, `GET /v1/policy-tests/{id}`, `POST /v1/policies/{id}/enforce {override?: bool}`, `POST /v1/findings/{id}/verify-with-policy {policy_id, version?}`, `GET /v1/agents/{id}/versions/{vid}/blast-radius?policy_id=`, `GET /v1/agents/{id}/permission-diff?from={vid}&to={vid}&policy_id=`.

**Decisions:**
- **The loop** (each step is its own route and job so the web console and CLI can show state): (1) **Suggest**: `suggest-policy` calls L8 `suggest_rule(finding)`, wraps it into a draft policy (`Policy` with that one rule, `mode="shadow"`, new version of the agent's policy or a new policy `pol_<finding suffix>`), stores it with the finding's `suggested_policy`. (2) **Offline test**: runs the L8 offline tester over stored trajectories: attack set = episodes of the finding's agent version (all runs, including campaigns and pinned regressions) whose objective held, benign set = counted `passed` episodes of recent eval runs (at most `max_benign`, default 200, newest first, stratified by scenario); result stored in `policy_tests.result` with the L8 report: block rate, false-positive rate, per-rule breakdown, tradeoff table, and per-trajectory first-block `seq`. (3) **Enforce**: `POST /policies/{id}/enforce` publishes a new version with `mode="enforce"` only if a completed `policy_test` exists for that policy version and its false-positive rate is at most `GAUNTLET_MAX_FP_RATE` (default 0.02) and block rate at least `GAUNTLET_MIN_BLOCK_RATE` (default 0.5); otherwise 409 `policy_test_required` or `policy_test_failed` with the numbers; `override=true` bypasses and is audited. (4) **Verify live** (`verify-with-policy`): re-runs the pinned reproducer for `reproducibility[1]` repetitions plus the benign smoke suite (the `smoke` suite of the finding's pack, else the workspace's `smoke` suite) with the policy enforced (`runs.policy_id`); the result is attached to the finding as a `finding_episodes` row with role `verification`; zero attack successes and benign pass rate not lower than the same suite without policy by more than the margin sets the finding `verified` (note "verified with policy <id> v<n>"), else it stays open with the numbers in a note. The counterfactual limitation is stated in every offline-test response: `"approximation": "replayed trajectories; the agent might take another route after a block"` (hard-cores 7.2).
- **GuardedWorld.** `call_tool` (a) emits the `tool_call` event as `World` does, (b) asks `session.check_tool_call(tool, args)`; on `block` it emits a `tool_result` with `ok=false`, `error="blocked_by_policy: <message>"`, `patch=[]`, origin `system`, and a `sim_note` event `{note: "policy_block", rule_id, action, kind: "guard"}`; it does not execute the tool, and since the decision is pure no effect is recorded (the call index counters are advanced identically so replay stays aligned); on `require_approval` in a simulated episode the approval handler is an auto-deny (simulation has no human; configurable `approve_all` for what-if runs, default deny); on `allow`/`log` it delegates to `World.call_tool` and then `session.record_tool_result(...)` with `untrusted` from the tool spec. The guard session in an episode uses the simulated clock and an in-memory sink so decisions can be read back as events. The runner builds a fresh `Guard` per episode from `EpisodeJob.policy` (enforced mode regardless of the stored mode when a verification run sets `policy_mode_override="enforce"`).
- **Blast radius** (`GET .../blast-radius`): per tool of the agent's world: `risk`, `collections_written` (from `crud` handler collections, and for `python` handlers the collections seen in patches of stored episodes), `max_records_changed_per_call` observed, `calls_observed`, `covered_by_rules: [rule_id]` (rules whose `when` references the tool), `approval_required: bool` (a `require_approval` rule covers it), `worst_case`: a one-line plain description built from risk and collections ("can issue refunds on any order; observed up to 1 order per call"). Overall `exposure_score`: sum of weights per uncovered tool (read 0, write 1, external_comm 2, destructive 3, financial 3, doubled when `untrusted_output` tools exist in the same world); shown with and without the supplied policy so the effect of a rule set is visible.
- **Permission diff** (`GET .../permission-diff`): between two agent versions (via their `world_id` and `HostedTargetConfig.tools` subsets): `added_tools`, `removed_tools`, `risk_changes` (risk class upgrades), `schema_widenings` (properties added, `required` entries removed, `enum` values added, `type` widened), `newly_uncovered` (tools whose coverage by policy rules dropped), plus `exposure_score` delta. Pure function over `ToolSpec`s and policies; tested with crafted pairs. Used by the web "what changed in permissions" panel and by `gauntlet gate` as an optional `permissions` gate (new `risk>=financial` tool without a covering rule fails).
- **Audit**: every enforce, override and verification writes an audit row; policy versions referenced by runs are immutable (P4-1).

**Steps:**
- [ ] `test_guarded_world.py`: allowed call equals plain `World` behaviour (journal identical apart from added `sim_note`s only on blocks); block produces the error tool result and no state patch; call counters stay aligned so resume and strict replay still pass; `require_approval` auto-deny and `approve_all`; shadow mode never blocks.
- [ ] `test_blast.py`: crafted tool sets and policies for exposure scores, coverage computation, permission-diff cases (new financial tool, widened schema, risk upgrade, removed tool, newly uncovered).
- [ ] `test_policy_tests_job.py` (integration, hand-built trajectories with known block points): block rate and FP rate match the known values, attack/benign sets assembled per the rules, stratification, `approximation` flag present. `test_loop_routes.py`: suggest creates a draft policy tied to the finding; enforce gating (missing test, failing numbers, override audited). `test_verify_with_policy.py`: a vulnerable scripted agent with the suggested rule enforced yields zero reproducer successes and the finding becomes `verified`; a rule that blocks benign behaviour leaves it open with numbers.
- [ ] `test_blast_routes.py`: shapes and scoping. `tests/integration/test_closed_loop.py` (compose, scripted DVA, FakeLLM): campaign finds a finding, suggest, offline test, enforce, verify, finding `verified`, audit rows present.
- [ ] Implement; **G** and integration. Commits: `feat(gateway): guarded world`, `feat(server): policy tests, enforcement gate, verify with policy`, `feat(policy): blast radius and permission diff`.

**Done when:** `tests/integration/test_closed_loop.py` passes end to end (finding to suggested rule to offline test to enforce to live verification to `verified`), and the permission diff of two DVA versions lists the added tool with its risk.

---

## Contract questions (Phase 4)

| ID | Question or gap |
|---|---|
| CQ-G1 | L8 and L5 public names needed here: `PolicyEngine` constructor, `GatewayDecision` fields (including a `modified` text for `redact`), the prefix and proposed-action types and how to build them from live events, the prefix-evaluability validator, the offline tester entry point and report type, `suggest_rule`. Fix them before batch n starts. |
| CQ-G2 | Policy and gateway tables and routes (`policies`, `policy_proposals`, `policy_tests`, `gateway_decisions`, `gateway_approvals`) are proposals (CQ-W24). Ratify names, the approval expiry semantics and the stats shape. |
| CQ-G3 | `runs.policy_id`/`policy_version` and a runner-level `EpisodeJob.policy` are needed to verify with a policy enforced; `RunManifest` is locked, so the policy reference is a column. Confirm, or add an optional field to the manifest. |
| CQ-G4 | The `redact` policy action needs a defined redaction behaviour (what is replaced, with what) and a `modified` field on the decision. Contracts section 7 says only `action: redact`. |
| CQ-G5 | `PolicyRule.strict` and `Policy.fail` are in the code but section 7 of the contracts does not list `strict`; confirm that `strict` is intended contract (hard-cores 7.1 uses it). |
| CQ-G6 | MCP tool risk for policy matching comes from annotation hints and config overrides because MCP tools carry no `risk` class; confirm this mapping or require a risk declaration in `gateway.yaml` for every tool. |
| CQ-G7 | Injection classifier model choice and licence need sign-off (default `protectai/deberta-v3-base-prompt-injection-v2`; alternatives gated or under other licences). Is a model download in the user's environment acceptable, and should the extra be shipped in the default install or opt-in (this plan assumes opt-in)? |
| CQ-G8 | Prod session identity: the SDK uses a caller-supplied `session_id` and `user_id`; whether the gateway needs authenticated end-user identity for per-user rules (spec 9.3 "per user role") is not specified. Deferred in this plan; confirm. |
