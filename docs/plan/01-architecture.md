# Architecture

## 1. The shape in one paragraph

Gauntlet is a Python library first and a platform second. `gauntlet_core` is a pure engine: given a scenario, a target and a model gateway, it runs an episode, records a journal, evaluates it and returns verdicts, with no database, web server or queue required. Everything else is a shell around that library: a CLI that runs it in-process with SQLite, a FastAPI control plane plus Postgres-backed workers that run it at scale, and a Next.js dashboard that reads what the workers wrote. This is what makes the free scanner CLI, local mode, fast tests and the hosted product the same code.

## 2. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language (backend) | Python 3.12 | LLM ecosystem, matches existing projects |
| Packaging | `uv` workspace | One lockfile, fast |
| Schemas | Pydantic v2 | Validation, JSON Schema export for the web client and YAML packs |
| API | FastAPI, Uvicorn | Async, OpenAPI for free |
| Database | PostgreSQL 16 with `pgvector` | Metadata, journals as JSONB, clustering vectors. No separate trace or vector store until volume demands it |
| ORM and migrations | SQLAlchemy 2 (async, `asyncpg`), Alembic | Standard |
| Queue and durable execution | **Custom, on Postgres** (`FOR UPDATE SKIP LOCKED` leases plus an append-only journal). No Celery. | Episodes are long, expensive, and must resume mid-conversation without repeating side effects. A task queue gives at-least-once delivery of whole jobs, which is the wrong primitive. See `03-hard-cores.md` section 1 |
| Cache and rate limits | Redis 7 | Provider token buckets, SSE fan-out via pub/sub, judge response cache |
| Object storage | S3-compatible (MinIO in compose) | Cassette exports, reports |
| LLM access | LiteLLM SDK in-process, behind `gauntlet_core.llm.Gateway` | Multi-provider, BYO keys, cost data. OpenRouter is the default provider so free and cheap tiers work |
| Local store | SQLite via `aiosqlite` | CLI and local mode, same store protocols |
| CLI | Typer, Rich | |
| Web | Next.js (App Router), TypeScript, Tailwind, **Animate UI** on shadcn, TanStack Query, `openapi-typescript` | Animate UI is the only component source |
| Live updates | Server-sent events | One-directional, simple, works through proxies |
| Monorepo | pnpm workspace plus Turborepo for JS; uv workspace for Python | |
| Tests | pytest, pytest-asyncio, Hypothesis, respx; Vitest; Playwright | |
| Lint and types | ruff, pyright; eslint, tsc | |
| Containers | Docker, docker compose | |
| CI | GitHub Actions | |

Default model roles (all configurable in `gauntlet.toml`, never hardcoded in logic): `simulator` and `judge_small` use a small cheap model, `judge_strong` and `attacker` use a strong one, `generator` uses a mid one. Model IDs are looked up at build time with the `claude-api` skill and OpenRouter docs, not from memory.

## 3. Repository layout

```
agent-security/                      (own git repo: run `git init` here in Phase 0)
  packages/
    core/        gauntlet_core       pure engine library
    server/      gauntlet_server     FastAPI app, Postgres stores, worker loop, Alembic
    cli/         gauntlet_cli        `gauntlet` command, local mode, scanner
  apps/
    web/                             Next.js dashboard
    dva/                             Damn Vulnerable Agent reference targets
  packs/                             scenario packs as YAML plus Python handlers
  attacks/                           attack library as YAML
  infra/                             docker-compose.yml, Dockerfiles
  tests/
    integration/  chaos/  live/
  docs/plan/                         this plan
```

`gauntlet_core` internal layout:

```
schema/     pydantic models: the locked contracts (02-contracts.md)
engine/     journal, effects, episode loop, budget, cassette, redact, store protocols + memory/sqlite stores
world/      state, patches, diff, tool specs and handlers, openapi import, faults, clock, canaries
targets/    Target protocol; hosted (harness runs the tool loop), openai_compat, http
sim/        user simulator, persona rendering, persona guard, termination
llm/        Gateway over LiteLLM: roles, routing, cost, cache, FakeLLM
checks/     the check language: AST, final evaluation, prefix (online) evaluation
eval/       deterministic evaluators, judges, cascade, evidence validation, calibration, scoring
stats/      intervals, pass^k, paired comparison, sequential stopping
security/   attack schema, objectives, injection harness, attacker loop, taint markers, shrinking
policy/     policy documents, engine, offline policy testing
gateway/    runtime enforcement middleware (Phase 4)
```

Import rule: `core` imports nothing from `server` or `cli`. Inside core, `schema` imports nothing else; `stats` and `checks` import only `schema`.

## 4. Decisions that shape everything

### D1. Three ways to put an agent under test

How the agent's tools reach the mock world is the central integration question. A black-box HTTP agent calls its own real tools, which the platform cannot see or control. So there are three target modes, in order of how much Gauntlet can verify:

1. **Hosted** (MVP, most powerful): the user gives a system prompt, a model and tool schemas. Gauntlet runs the agent's tool loop itself and every tool call goes to the mock world. Full visibility, full state verification, full replay. This covers "test my prompt and tools before I ship" and is what the onboarding wizard uses.
2. **Wired** (MVP, used by DVA; documented for users): a remote agent whose tool base URL or MCP server URL is pointed at Gauntlet's per-episode mock endpoint (`/mock/{episode_token}/...`). The agent runs its own loop; Gauntlet sees every tool call because it is serving them. The connector passes the episode token to the agent in a header (`X-Gauntlet-Episode`).
3. **Black-box** (MVP): conversation only. No world state, no tool visibility. Conversation-level evaluators, canaries planted in the conversation and output scanning still work. Reports label reduced coverage clearly.

Gray-box trace ingestion (OpenTelemetry) is Phase 5.

### D2. One journal gives resume, replay and re-judging

An episode is an append-only journal of events. Every non-deterministic step (model call, target call, tool execution) is an *effect* whose result is recorded. Re-running an episode over an existing journal returns recorded results instead of re-executing. That single mechanism provides crash recovery, exact replay (cassettes are exported journals), and re-running new evaluators over old runs without paying for the agent again.

### D3. One check language for criteria, objectives, policies and gateway rules

Scenario success criteria, attack success conditions, compiled policy rules and runtime gateway rules are all expressions in one small declarative language (`gauntlet_core.checks`). An expression can be evaluated over a finished trajectory (testing) or over a trajectory prefix plus a proposed action (enforcement). This is how "the same rules feed tests and the gateway" becomes literally true, and how a red-team finding turns into a gateway rule that is then tested offline against recorded attack and benign trajectories.

### D4. Deterministic first, and evidence is machine-validated

Evaluation order is rules, then a small judge, then a strong judge only when needed. Judge criteria are binary (pass, fail, not applicable) by default, because binary judgments agree with humans far better than 1 to 5 scales; anchored scales are available for tone-type rubrics only. Every judge verdict must cite `(event seq, quote)` pairs and the platform verifies each quote is actually present in that event. A verdict with invalid evidence is discarded.

### D5. Outcomes separate the agent from everything else

An episode ends as exactly one of: `passed`, `failed`, `invalid_scenario`, `simulator_error`, `target_error`, `platform_error`, `budget_exhausted`. Only `passed` and `failed` count in agent statistics. This keeps platform and simulator noise out of the numbers.

### D6. Statistics are per scenario, then across scenarios

Trials of one scenario are not independent of each other in the way trials across scenarios are. All suite-level intervals and comparisons resample scenarios (cluster bootstrap), and comparisons between two runs are paired by scenario.

### D7. Multi-tenant columns from day one, single-tenant behaviour in the MVP

Every table has `workspace_id`. The MVP ships with one workspace, API-key auth and a single admin login. Real sign-up, roles and SSO are deferred. Adding them later does not need a schema rewrite.

### D8. Attack payloads come from open sources

The attack library is seeded by importing openly licensed probe sets (garak, promptfoo red-team plugins, AgentDojo, InjecAgent) with source and licence recorded per entry. Gauntlet's own contribution is the harness around them: objectives, placement, mutation, adaptivity, shrinking, and closing the loop. Attack suites run only against hosted targets, local targets, or remote targets that passed ownership verification.

## 5. Runtime topology

```
           dashboard (Next.js) ──HTTP/SSE──┐
           CLI / CI / GitHub Action ───────┤
                                           ▼
                                   api (FastAPI)  ──── Postgres (metadata, journals, queue, vectors)
                                           │      ──── Redis (rate limits, pub/sub, cache)
                                           │      ──── MinIO (cassettes, reports)
                                           ▼
                               worker × N (asyncio)
                     claims episodes, runs gauntlet_core, appends journal
                          │              │                │
                   model gateway    target agent     mock world
                    (LiteLLM)     (hosted / wired /   (in-process state;
                                    black-box)        HTTP + MCP façade for wired targets,
                                                      served by api, routed to the owning worker's state via Postgres)
```

Local mode collapses this to one process: the CLI builds a `gauntlet_core` runner with SQLite stores and an asyncio semaphore.

For wired targets the mock façade must reach the world state of a specific in-flight episode. World state is rebuilt from the journal on demand (it is a fold over recorded patches), and tool calls from the façade are appended through the same journal with the same lease, so the façade can run in any api process. Detail in `03-hard-cores.md` section 2.6.

## 6. What is deliberately not built

Voice, browser and computer-use targets, multimodal attacks, framework adapters (LangGraph and the rest), SSO and SCIM, the review marketplace, a separate analytics database, and per-role dashboards are out of scope for this plan. They are listed in `04-roadmap.md` under Deferred so nobody builds toward them by accident.
