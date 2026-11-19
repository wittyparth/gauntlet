# Gauntlet build plan: how to use it

Gauntlet is an agent testing, simulation and security platform. The product vision lives in the two spec files at the repo root (`agent-testing-platform-plan.md`, `agent-testing-platform-realworld-addendum.md`). This folder turns that vision into something buildable.

## Reading order

| File | What it decides | Who reads it |
|---|---|---|
| `README.md` (this file) | Workflow, ownership, quality gates, tools and skills | Everyone, every session |
| `01-architecture.md` | Tech stack, repo layout, the architectural decisions and why | Everyone, once |
| `02-contracts.md` | Locked data models, interfaces, DB tables, API shape | Every implementer, every task |
| `03-hard-cores.md` | Designs for the difficult parts (engine, world, stats, checks, judges, security, policy) | Lead; implementers who consume those modules |
| `04-roadmap.md` | Phases, the task index with IDs, owners, dependencies, cut lines | Lead, to dispatch work |
| `phases/*.md` | Detailed per-task instructions for subagent-owned tasks | The subagent doing that task |

## Ownership model

The lead model (Fable or Opus, main session) **orchestrates and reviews; it does not write product code.** All code is written by Sonnet subagents (`model: "sonnet"`). Never spawn subagents on the top-tier model.

Two kinds of task, marked in `04-roadmap.md`:

- **[CORE]** tasks (L-numbered) are the parts where a subtle mistake poisons everything downstream: engine, world, statistics, check language, judge cascade, security core, policy engine. Their full designs are in `03-hard-cores.md`. A Sonnet agent implements one from that design; the lead reviews the diff line by line against the design and its invariants before merging. L1, L2, L3 are done.
- **[SUB]** tasks are everything else (connectors, API, CLI, dashboard, packs, imports, reports, integrations), detailed in `phases/`.

Rules for dispatching [SUB] work:

1. Batch heavily: one agent per large batch (a whole roadmap batch letter or more), never one agent per file or small task. Run one agent at a time, at most two when their files do not overlap.
2. The brief is short: the task IDs, the phase file path, and "read `docs/plan/README.md` and `docs/plan/02-contracts.md` first". The phase file carries the detail. Do not retype it.
3. Subagents never change `02-contracts.md` or anything under `packages/core/src/gauntlet_core/schema/`. If a contract is wrong or missing, they stop that task and report the gap. The lead decides and records it in the decision log at the bottom of `02-contracts.md`.
4. The lead merges worktrees, runs the full gate, and reviews at every phase boundary.

## Task lifecycle (every task, lead or sub)

1. Read the task, its `Consumes` and `Produces` interfaces, and the contract sections it names.
2. Write the failing test first. Run it and see it fail for the right reason.
3. Implement the minimum that passes.
4. Run the task's gate (below). Fix until green.
5. Commit with a conventional message (`feat(core): ...`, `fix(api): ...`). One task, one or a few small commits.
6. Report: what was built, test output, anything skipped, any contract question.

## Quality gates

Run from the repo root. A task is not done until its gate is green.

| Scope | Command | Must show |
|---|---|---|
| Python unit | `uv run pytest packages -q` | all pass |
| Python lint and types | `uv run ruff check . && uv run ruff format --check . && uv run pyright packages` | clean |
| Web | `pnpm --filter web lint && pnpm --filter web typecheck && pnpm --filter web test` | clean |
| Integration (needs compose) | `docker compose -f infra/docker-compose.yml up -d && uv run pytest tests/integration -q` | all pass |
| End to end | `pnpm --filter web e2e` (Playwright against the compose stack and the DVA support agent) | all pass |
| Engine chaos | `uv run pytest tests/chaos -q` | all pass, see `03-hard-cores.md` section 1.7 |

Testing rules:

- **No live LLM calls in unit or integration tests.** Use `FakeLLM` (scripted responses) or a committed cassette. Live calls happen only in `tests/live/`, which is opt-in via `GAUNTLET_LIVE=1` and has a dollar cap.
- Every evaluator, check node and statistic gets property tests (Hypothesis) in addition to examples.
- Every connector gets a contract test against a local fake server.
- Every dashboard screen gets one Playwright test that loads it with seeded data and asserts the key content is visible.

## Verifying UI for real

A screen is done only after it has been looked at in a browser, not just type-checked:

1. Start the stack (`docker compose up -d`, `pnpm --filter web dev`), seed with `uv run gauntlet demo seed`.
2. Drive the screen with Playwright (preferred, scriptable) or the Claude-in-Chrome browser tools. Take a screenshot, read console errors.
3. Check the golden path, the empty state, the loading state and one error state.

## Skills and tools to use

| Situation | Use |
|---|---|
| Any dashboard UI work | `animate-ui` skill. **Mandatory.** Every component comes from Animate UI (or the shadcn base it installs). No custom-built components, no other UI kits. If Animate UI has no fit, compose its primitives; if that fails, report it to the lead rather than hand-rolling. |
| Layout, hierarchy, visual direction of a screen | `frontend-design:frontend-design` and `impeccable`, within the Animate UI constraint |
| Simulator prompts, judge prompts, attacker loop, LLM routing, caching | `ai-engineer` skill |
| Anything calling Anthropic models | `claude-api` skill, for current model IDs and parameters |
| A failing test or unexpected behaviour | `superpowers:systematic-debugging` before changing code |
| Before saying a task is done | `superpowers:verification-before-completion` |
| Library or API details you are unsure of | Firecrawl or Exa developer search. Do not guess at library APIs. |
| Charts in the dashboard | `dataviz` skill |

## Conventions

- Python 3.12, `uv` workspace, `ruff` (line length 100), `pyright` strict on `packages/core`, standard on the rest. Pydantic v2 models, `async` I/O everywhere, no global state.
- TypeScript strict, pnpm workspace, Turborepo. The web app never hand-writes API types: they are generated from the FastAPI OpenAPI document (`pnpm --filter web gen:api`).
- IDs are prefixed ULIDs: `ws_`, `proj_`, `agt_`, `ver_`, `scn_`, `per_`, `suite_`, `run_`, `ep_`, `fnd_`, `atk_`, `pol_`.
- Money is integer micro-dollars (`usd_micros`). Never floats for cost.
- Time in episodes comes from the simulated clock, never `datetime.now()` inside the engine.
- Secrets never enter events, logs or cassettes. The redaction filter in `gauntlet_core.engine.redact` runs on every journal append.
- Files stay small and single-purpose. If a file passes about 400 lines, split it.
- Each package has a short `README.md` saying what it owns and what it must not import.

## Scope discipline

The specs describe far more than will be built. `04-roadmap.md` says what is in each phase and what is explicitly deferred. If a task seems to need something deferred, it does not: build the smaller thing.
