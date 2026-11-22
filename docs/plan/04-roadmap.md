# Roadmap and task index

Each task has an ID, an owner, and dependencies. **[CORE]** (L-numbered) tasks are designed in `03-hard-cores.md`, implemented by a Sonnet agent and reviewed line by line by the lead. **[SUB]** tasks are detailed in `phases/` and implemented by Sonnet subagents in batches (the batch letter says which tasks go to one agent together).

Each phase ends with something demonstrable and a lead review (architecture drift, security of the platform itself, contract changes, refinement of the next phase).

## Phase 0: Foundations

| ID | Owner | Task | Depends |
|---|---|---|---|
| P0-1 | SUB a | `git init`, uv workspace (`core`, `server`, `cli`), pnpm + Turborepo, ruff, pyright, pytest config, pre-commit, `.gitignore`, package READMEs | |
| P0-2 | SUB a | `infra/docker-compose.yml`: Postgres 16 + pgvector, Redis 7, MinIO, api, worker; Dockerfiles; `.env.example` | P0-1 |
| P0-3 | SUB a | GitHub Actions: lint, types, unit, integration against compose services | P0-1 |
| L1 | DONE | `gauntlet_core.schema`: every model in `02-contracts.md` sections 1 to 5, YAML load and dump, JSON Schema export | P0-1 |

## Phase 1: Vertical slice

Definition of done: `gauntlet run packs/ecommerce --target hosted.yaml` prints a credible report locally; the same run from the dashboard streams live, and the episode viewer shows transcript, tool timeline, state diff and verdicts with evidence. Demonstrated against the DVA support agent.

| ID | Owner | Task | Depends |
|---|---|---|---|
| L2 | DONE | Engine: effects, journal, episode loop, budget, cassette, memory and SQLite stores, redaction | L1 |
| L3 | DONE | World: state, patches, diff with causal seq, crud and python handlers, faults, clock, canaries | L1 |
| L4 | DONE | Stats: Wilson, bootstrap, pass^k, comparison, flips, sequential, agreement | L1 |
| L5 | DONE | Checks: AST, final and prefix evaluation, matcher and ref resolution, detector registry | L1, L3 |
| L6 | DONE | Judges: rendering, evidence validation, cascade, cache, calibration, simulator guard | L1, L4, L5 |
| P1-1 | SUB b | LLM gateway over LiteLLM: roles from `gauntlet.toml`, cost, retries, rate limiting, `FakeLLM`, structured output | L1 |
| P1-2 | SUB b | Targets: hosted (tool loop through `ctx`), openai_compat, http; contract tests with a fake server | L2, P1-1 |
| P1-3 | SUB b | User simulator: persona rendering, hidden facts, turn prompt, done detection; 10-persona library | L2, P1-1 |
| P1-4 | SUB c | Deterministic detectors: pii, secret, profanity, markdown_image_exfil, loop, commitment_phrase | L5 |
| P1-5 | SUB c | Rubric library v1 (task completion, groundedness, policy adherence, hallucinated policy, binding commitment, tone, escalation) with examples; scoring and report aggregation | L6, L4 |
| P1-6 | SUB c | E-commerce pack: world (6 tools, seed data, python handlers), 30 scenarios, policy text, checks | L3, L5 |
| P1-7 | SUB c | OpenAPI import to `ToolSpec` + seed; scenario auto-generation from agent profile (drafts) | L3, P1-1 |
| P1-8 | SUB d | Server: SQLAlchemy models, Alembic, Postgres `JournalStore`, `EpisodeQueue`, `BudgetLedger` per `03` section 1.4 and 1.5 (lead reviews this one line by line) | L2 |
| P1-9 | SUB d | Server: REST API per contracts section 9, API-key auth, secrets, SSE stream via Redis pub/sub, worker process | P1-8 |
| P1-10 | SUB d | CLI: `gauntlet run`, `init`, `validate`, `report`, `demo seed`, local SQLite mode, JSON output and exit codes | L2, P1-5 |
| P1-11 | SUB e | DVA support agent (`apps/dva`): wired target with a catalog of planted flaws (`apps/dva/CATALOG.md`), plus a hosted-config variant | P1-6 |
| P1-12 | SUB f | Web foundation: Next.js, Animate UI setup, app shell, generated API client, auth | P1-9 |
| P1-13 | SUB f | Web: onboarding wizard, agent overview, scenario list and viewer | P1-12 |
| P1-14 | SUB f | Web: run console (live SSE), run report, episode viewer (transcript, tool timeline, state diff, verdicts with evidence highlighting) | P1-12 |
| L-R1 | DONE | Chaos test of engine on Postgres; phase review; end-to-end verification in a browser | all |

## Phase 2: Security core

Definition of done: an attack suite against DVA produces findings with deterministic evidence; one finding shrinks to a few lines; detection recall against the DVA catalog is measured and printed.

| ID | Owner | Task | Depends |
|---|---|---|---|
| L7 | DONE | Security core: objectives, injection harness, taint markers, attacker loop, shrinking, finding creation and dedup, verify | L5, L6 |
| P2-1 | DONE | Threat taxonomy file with OWASP LLM / agentic and MITRE ATLAS mapping; attack YAML schema loader | L7 |
| P2-2 | DONE | Attack library import: garak, promptfoo, AgentDojo, InjecAgent probes normalised to `Attack` with source and licence; target 100+ across categories 1 to 8, 11 | P2-1 |
| P2-3 | DONE | Mutation engine: paraphrase, translate, encode, roleplay wrap, split across turns, embed in document | P2-1 |
| P2-4 | DONE | Ownership verification for remote targets, scope controls, audit log of attack runs, kill switch | P1-9 |
| P2-5 | DONE | Findings API, lifecycle, replay, regression pinning into a `security-regression` suite, SARIF and markdown export | L7 |
| P2-6 | DONE | Security posture report (coverage heatmap data, top findings, tool permission review) | P2-5 |
| P2-7 | DONE | Hall of Failures pack: 8 incident-derived scenarios (Air Canada, Chevrolet, DPD, MyCity, Replit, Cursor, Slack AI, EchoLeak), sources verified and cited neutrally | L7 |
| P2-8 | DONE | MCP scanner v1 and agent linter v1 as CLI commands (`gauntlet scan mcp`, `gauntlet lint`) | P2-1 |
| P2-9 | DONE | DVA: SQL agent and email assistant with planted vulnerabilities; recall script | P1-11 |
| P2-10 | DONE | Web: findings inbox and detail, campaign launch, coverage heatmap, posture report page | P2-5 |
| L-R2 | DONE | Phase review; measure recall and precision on DVA; publishable checkpoint | all |

## Phase 3: Regression and rigor

| ID | Owner | Task | Depends |
|---|---|---|---|
| P3-1 | DONE | Baselines, run comparison API using L4, flip table, trajectory diff | L4 |
| P3-2 | DONE | Repetitions, pass^k and reliability curve in reports; flaky scenario detection and quarantine; adaptive sampling switch | L4 |
| P3-3 | DONE | Cassette export and import, `strict` and `agent_live` replay from CLI and API, rejudge endpoint | L2 |
| P3-4 | DONE | GitHub Action, PR comment, gates (`gauntlet gate`), badge endpoint | P3-1 |
| P3-5 | DONE | Human review queue API, golden sets, calibration job and rubric gating using L6 | L6 |
| P3-6 | DONE | Failure clustering (embeddings in pgvector, HDBSCAN, model-named clusters), root-cause attribution | P1-9 |
| P3-7 | DONE | Web: compare view, reliability charts, review queue, rubric manager, clusters on run report | P3-1, P3-5, P3-6 |
| P3-8 | DONE | Model migration report (same suite on two versions, Pareto data), scorecard page | P3-1 |
| L-R3 | LEAD | Phase review; judge accuracy study on a hand-labelled set | all |

## Phase 4: Gateway and policies

| ID | Owner | Task | Depends |
|---|---|---|---|
| L8 | DONE | Policy engine, offline policy testing, rule suggestion from findings | L5, L7 |
| P4-1 | DONE | Policy compiler: policy document to proposed rules (typed machine, model, human), review flow, coverage report | L8 |
| P4-2 | DONE | Gateway as Python SDK middleware (wraps tool execution), shadow and enforce, decision log, approvals | L8 |
| P4-3 | DONE | MCP gateway: proxy, description pinning, allowlist, description scanning, namespace isolation | P4-2 |
| P4-4 | DONE | Injection classifier detector (open-source model, local), origin tagging in the middleware | P4-2 |
| P4-5 | DONE | Closed loop wiring: finding, suggested rule, offline test, enforce, verify; blast-radius and permission diff | L8, P2-5 |
| P4-6 | DONE | Web: gateway console, policy editor, policy test results with tradeoff chart, approval inbox | P4-2 |
| L-R4 | DONE | Phase review; latency benchmark; closed-loop demo recorded | all |

## Phase 5: Production loop, proof and launch

| ID | Owner | Task |
|---|---|---|
| P5-1 | SUB | OpenTelemetry / OpenInference trace ingestion with PII redaction |
| P5-2 | SUB | Failure mining and conversation-to-scenario conversion with anonymisation |
| P5-3 | SUB | Enterprise knowledge copilot pack with role-based identities and ACL leakage tests; banking pack |
| P5-4 | SUB | tau-bench retail and AgentDojo import; benchmark reproduction run |
| P5-5 | SUB | Meta-evaluation studies and benchmark page: DVA recall, judge agreement, reproducibility, cost per 1,000 episodes |
| P5-6 | SUB | MCP server for the platform; docs site; public challenge arena (one defended agent, levels, leaderboard) |
| P5-7 | SUB | SLOs, change-impact analysis, launch readiness review, compliance evidence pack export |
| L-R5 | LEAD | Final review, launch checklist |

Phase 5 tasks are specified to the level of the other phases only when Phase 4 is done, because what gets built there should follow what real users of Phases 1 to 4 ask for.

## Deferred (not planned; do not build toward)

Voice simulation, browser and computer-use targets, multimodal attacks, framework adapters, search-based attack strategies (genetic, beam, TAP), SSO and SCIM, fine-grained roles, per-role dashboards, community pack marketplace, threat-intel feed, incident response mode, chaos game days, cost-versus-human reports, natural-language analytics, reverse-proxy gateway form.

## Critical path

`P0-1 → L1 → L2 + L3 → L5 → L6 → (P1 batches in parallel) → L-R1 → L7 → (P2 batches) → L8 → (P4 batches)`. L4 is independent after L1 and can be done any time before P1-5.

## Execution order (agents, one at a time)

| # | Agent batch | Contents |
|---|---|---|
| 1 | core-a | L5 checks + L4 stats |
| 2 | core-b | L6 judges + P1-1 LLM gateway + P1-4 detectors |
| 3 | infra | P0-2, P0-3, P1-8 (compose, CI, Postgres store, queue, ledger, SQLite store, shared store contract tests) |
| 4 | runtime | P1-2 targets, P1-3 simulator, P1-5 rubrics and scoring, P1-10 CLI and runner |
| 5 | server + content | P1-9 API, worker, SSE, api-process mock facade; P1-6 e-commerce pack; P1-7 OpenAPI import; P1-11 DVA |
| 6 | web-1 | P1-12, P1-13, P1-14 (uses the `animate-ui` skill) |
| 7 | lead | L-R1 review, chaos test run, browser verification |

Phases 2 to 4 follow the same shape: one core agent for the L task, then one or two batches of SUB tasks, then web, then the lead review.
