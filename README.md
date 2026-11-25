# Gauntlet

Test, attack, and guard your AI agents.

Gauntlet is an open-source platform (Apache-2.0) for evaluating, red-teaming and runtime-guarding LLM agents. It is self-hosted and runs on cheap, non-frontier models.

## What it does

One loop: find, fix, prove.

- **Find.** Simulated users exercise your agent in a sandboxed world, and a library of 297 attacks red-teams it. Runs produce reports with cited evidence.
- **Fix.** A confirmed finding becomes a suggested runtime policy (allow, block, redact, approve). Policies are tested offline and enforced at a gateway.
- **Prove.** A verify run replays the original attack against the guarded agent. Reliability is reported as pass^k with confidence intervals, and recorded episodes can be replayed against new agent versions.

Quality of the judges is measured, not assumed: a blind review queue and rubric calibration report Cohen's kappa against reference labels, and a rubric that is not calibrated cannot gate.

## Surfaces

- **Web console** (`apps/web`, Next.js): runs, findings, policies, approvals, benchmarks, and a public arena where visitors try to break a defended agent.
- **CLI** (`gauntlet`): `scan mcp`, `lint`, `gate`, `mcp pin` / `mcp diff` (tool-definition pinning), `evidence`, plus `run`, `report`, `replay`, `impact`, `policy`, `attacks`.
- **MCP server** (`packages/mcp_server`, `gauntlet-mcp`): lets coding agents drive a Gauntlet platform with read tools and a capped, confirmed run creation.
- **GitHub Action** (`integrations/github-action`): runs a suite on a PR, evaluates gates, keeps one PR comment current and can publish a badge. See its README.
- **OTLP ingest:** production traces come in with PII redaction and can be mined into draft scenarios.

## Quickstart

Local, no API key, no model spend (a scripted fake LLM answers). Needs Python 3.12 and [uv](https://docs.astral.sh/uv/):

```sh
uv sync
uv run gauntlet validate docs/user/examples/tinyshop
uv run gauntlet run docs/user/examples/tinyshop --target docs/user/examples/agent.yaml \
  --suite smoke --fake-llm docs/user/examples/fake_llm_smoke.yaml --out runs/quickstart
uv run gauntlet report runs/quickstart
```

Local platform (Postgres, Redis, MinIO, API, worker) and web console; see `infra/README.md` for the env file step:

```sh
docker compose -f infra/docker-compose.yml up -d --build --wait
curl -fs localhost:8000/healthz
cd apps/web && pnpm install && pnpm dev
```

More in `docs/user/quickstart.md`.

Single-VPS deploy (Docker Compose plus Caddy; Ubuntu or Debian, 4 GB RAM or more; Oracle free tier, Hetzner and Coolify/Dokploy are covered):

```sh
git clone https://github.com/wittyparth/gauntlet /opt/gauntlet && cd /opt/gauntlet
sudo ./deploy/bootstrap.sh --domain gauntlet.example.com      # omit --domain for a plain-HTTP IP demo
GAUNTLET_API_KEY=<key printed at the end> BASE_URL=https://gauntlet.example.com scripts/demo_smoke.sh
```

Details, variables, backups and the security checklist: `deploy/README.md`.

## Results, including the unflattering ones

- [DVA recall, live run](docs/benchmarks/dva-recall-live-2026-11.md): the red team found 4 to 6 of 12 planted flaws in the Damn Vulnerable Agent across runs. A full 297-attack run cost $0.24.
- [Judge agreement](docs/benchmarks/judge-agreement-2026-11.md): Cohen's kappa against Claude Opus reference labels (not human graders) is 0.62 for `task_completion` and 0.71 for `policy_adherence`. Both are below the 0.8 gate, so these judges are not yet calibrated to gate on.

More in [docs/benchmarks/index.md](docs/benchmarks/index.md). Studies are pre-registered and reproducible from `studies/` (see `studies/README.md`).

## Models and cost

Gauntlet targets cheap, non-frontier models through OpenRouter, for example DeepSeek V4 Flash, Qwen3.7 Flash and Gemini 2.5 Flash-Lite (catalog: `packages/core/src/gauntlet_core/llm/catalog.py`). Live model calls happen only when `OPENROUTER_API_KEY` is set. Spend is capped per run (`--budget-usd`, `GAUNTLET_MAX_RUN_BUDGET_USD_MICROS`) and per day (`GAUNTLET_DAILY_BUDGET_USD`).

## Repository layout

- `packages/core`, `packages/server`, `packages/cli`, `packages/mcp_server`: engine, API and worker, CLI, MCP server
- `apps/web`: console and landing page; `apps/dva`: Damn Vulnerable Agent targets (intentionally vulnerable, never expose them); `apps/arena`: public arena
- `packs/`: scenario packs (ecommerce, banking, enterprise copilot, arena, hall of failures)
- `attacks/`: attack library
- `integrations/github-action`: CI gate
- `studies/`: benchmark and calibration studies
- `deploy/`, `infra/`: production and local compose stacks
- `docs/`: user docs (`docs/user`), plan, benchmarks

## License

Apache-2.0, see `LICENSE`.
