# Phase 0: foundations (P0-1, P0-2, P0-3)

Batch a, one Sonnet agent, order P0-2 then P0-3. Read first: `docs/plan/README.md`, `docs/plan/01-architecture.md` sections 2, 3, 5.

Gate for Python tasks in this phase (called **G** in every phase file): `uv run ruff check . && uv run ruff format --check . && uv run pyright packages && uv run pytest packages -q`.

---

### P0-1: Repo and workspace (DONE)

The uv workspace (`core`, `server`, `cli`), ruff (line 100), pyright, pytest config (asyncio auto, `--import-mode=importlib`), `.gitignore` and the git repo exist (commits `9797645`, `c20e27d`).
Not done and absorbed by P0-3: `.pre-commit-config.yaml`, per-package `README.md`, root `package.json` + `pnpm-workspace.yaml` + `turbo.json` (the web scaffold in P1-12 adds `apps/web` to them).

---

### P0-2: Docker compose, Dockerfiles, env

**Batch:** a  **Depends:** P0-1

**Files:**
- Create: `infra/docker-compose.yml`, `infra/.env.example`, `infra/docker/python.Dockerfile`, `infra/postgres/init/10-init.sh`, `infra/minio/init.sh`, `.dockerignore`, `infra/README.md` (how to start, ports, reset volumes, scale workers)
- Create (stubs, replaced by P1-8/P1-9, keep the names): `packages/server/src/gauntlet_server/app.py` (FastAPI app, only `GET /healthz` returning `{"status":"ok","version":<pkg version>}`), `packages/server/src/gauntlet_server/worker.py` (`async def main()`: logs "worker started", loops `await asyncio.sleep(5)` until SIGTERM, exits 0; `if __name__ == "__main__": asyncio.run(main())`)
- Modify: `packages/server/pyproject.toml` (add `fastapi>=0.115`, `uvicorn[standard]>=0.30`; dev: `httpx`)
- Test: `packages/server/tests/test_app_health.py`

**Interfaces:**
- Consumes: nothing from core.
- Produces: the compose project `gauntlet` with services below; env var names (the contract every later task uses); module paths `gauntlet_server.app:app` and `python -m gauntlet_server.worker`.

**Decisions:**

Services (all ports bound to `127.0.0.1`):

| Service | Image / build | Ports | Healthcheck | Notes |
|---|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | 5432 | `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB` every 3 s, 20 retries | volume `pgdata`; mounts `infra/postgres/init` to `/docker-entrypoint-initdb.d` |
| `redis` | `redis:7-alpine` | 6379 | `redis-cli ping` | command `redis-server --save "" --appendonly no` (cache and pub/sub only, nothing durable) |
| `minio` | `minio/minio` pinned to a dated `RELEASE.*` tag (look the current tag up; do not use `latest`) | 9000 (S3), 9001 (console) | `curl -f http://localhost:9000/minio/health/live` | volume `miniodata`; command `server /data --console-address ":9001"` |
| `minio-init` | `minio/mc` pinned | none | one-shot | runs `infra/minio/init.sh`: `mc alias set`, `mc mb --ignore-existing local/$S3_BUCKET`; `restart: "no"` |
| `migrate` | build `python.Dockerfile` target `api` | none | one-shot | `command: alembic -c /app/packages/server/alembic.ini upgrade head`; until P1-8 lands the command is `true` (leave a `# P1-8:` comment); `depends_on postgres: service_healthy` |
| `api` | build `python.Dockerfile` target `api` | 8000 | `python -c "import urllib.request as u; u.urlopen('http://localhost:8000/healthz')"` | `command: uvicorn gauntlet_server.app:app --host 0.0.0.0 --port 8000`; depends on postgres, redis (healthy), migrate (`service_completed_successfully`), minio-init (`service_completed_successfully`) |
| `worker` | same image, target `worker` | none | none | `command: python -m gauntlet_server.worker`; same depends_on; **no `container_name`** so `docker compose up --scale worker=3` works (the chaos test needs it); `stop_grace_period: 30s` (graceful lease release) |

`infra/postgres/init/10-init.sh` (POSIX sh, `set -e`): `psql` runs `CREATE EXTENSION IF NOT EXISTS vector;` on `$POSTGRES_DB`, then `CREATE DATABASE gauntlet_test;` and the same extension there. Tests use `gauntlet_test`, never the dev database.

`python.Dockerfile` (one file, multi-stage):
- `FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder`; copy `pyproject.toml uv.lock packages/*/pyproject.toml` first and run `uv sync --frozen --no-dev --no-install-workspace --package gauntlet-server` (dependency layer cached), then copy `packages/` and run `uv sync --frozen --no-dev --no-editable --package gauntlet-server`.
- Runtime base `python:3.12-slim-bookworm`; copy `/app/.venv`; `ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1`; non-root user `gauntlet` uid 10001; `WORKDIR /app`.
- Targets `api` and `worker` differ only in default `CMD`. Copy `packs/` and `attacks/` into the image if the directories exist (use a `COPY --chown ... packs/ ./packs/` guarded by a `.dockerignore`-safe empty dir created in the repo with `.gitkeep`).
- `.dockerignore`: `.git`, `.venv`, `node_modules`, `.omc`, `docs`, `apps/web/.next`, `**/__pycache__`, `infra/.env`.

`infra/.env.example` (every key with a comment; secrets are obvious placeholders, never real values):

| Key | Default |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `gauntlet` / `gauntlet-dev-only` / `gauntlet` |
| `DATABASE_URL` | `postgresql+asyncpg://gauntlet:gauntlet-dev-only@postgres:5432/gauntlet` |
| `TEST_DATABASE_URL` | `postgresql+asyncpg://gauntlet:gauntlet-dev-only@localhost:5432/gauntlet_test` (host-side, used by `uv run pytest`) |
| `REDIS_URL` | `redis://redis:6379/0` |
| `S3_ENDPOINT_URL` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` / `S3_BUCKET` / `S3_REGION` | `http://minio:9000` / `minio-dev` / `minio-dev-secret` / `gauntlet` / `us-east-1` |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | same as the S3 pair |
| `GAUNTLET_ENV` | `dev` (`dev` enables the fixed dev API key and unauthenticated `/openapi.json`; anything else disables both) |
| `GAUNTLET_DEV_API_KEY` | `gk_dev_local_only` |
| `GAUNTLET_SECRET_KEY` | empty; comment gives the generator: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `GAUNTLET_CONFIG` | `/app/gauntlet.toml` |
| `GAUNTLET_ALLOW_PRIVATE_TARGETS` | `false` |
| `GAUNTLET_LOCAL_TARGET_HOSTS` | `dva,localhost,127.0.0.1` |
| `WORKER_CONCURRENCY` / `LEASE_SECONDS` | `4` / `60` |
| `OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY` | empty |
| `LOG_LEVEL` | `info` |

Compose reads `infra/.env` automatically (project directory is the compose file's directory). `infra/.env` is gitignored (add the line if missing).

**Steps:**
- [ ] Write `test_app_health.py`: "healthz returns ok" (httpx `ASGITransport(app=app)`, `GET /healthz` -> 200, body `status == "ok"` and a `version` string). Run it; fails (no module).
- [ ] Implement `app.py` and `worker.py` stubs and the server dependencies. Test passes.
- [ ] Write `.env.example`, init scripts, Dockerfile, compose file, `.dockerignore`, `infra/README.md`. Run `cp infra/.env.example infra/.env`.
- [ ] `docker compose -f infra/docker-compose.yml config -q` (no output = valid).
- [ ] `docker compose -f infra/docker-compose.yml up -d --build --wait` (all healthy), then `curl -fs localhost:8000/healthz`.
- [ ] `docker compose ... exec postgres psql -U gauntlet -d gauntlet -c "select extname from pg_extension where extname='vector'"` returns a row; same for `-d gauntlet_test`.
- [ ] `docker compose ... up -d --scale worker=3` shows 3 worker containers running; `docker compose ... logs worker | grep "worker started"` has 3 lines.
- [ ] `docker compose ... down -v` leaves nothing. Gate **G**. Commit `chore(infra): compose stack, dockerfile, env template`.

**Done when:** from a clean clone, `cp infra/.env.example infra/.env && docker compose -f infra/docker-compose.yml up -d --wait` reaches all-healthy, `GET :8000/healthz` is 200, the MinIO console at `:9001` shows bucket `gauntlet`, the `vector` extension exists in both databases, and `G` is green.

---

### P0-3: GitHub Actions and repo hygiene

**Batch:** a  **Depends:** P0-1, P0-2

**Files:**
- Create: `.github/workflows/ci.yml`, `.github/workflows/nightly.yml`, `.pre-commit-config.yaml`, `conftest.py` (repo root), `packages/core/README.md`, `packages/server/README.md`, `packages/cli/README.md`, `package.json`, `pnpm-workspace.yaml` (`apps/*`), `turbo.json` (tasks `lint typecheck test build` with `dependsOn ["^build"]` on build only), `.github/dependabot.yml` (uv, github-actions, npm weekly)
- Modify: root `pyproject.toml` (register markers `integration`, `chaos`, `live`; keep `slow`)
- Test: `tests/test_marker_plumbing.py`

**Interfaces:**
- Consumes: the gate commands in `README.md`.
- Produces: pytest markers and the skip rule every integration test relies on; CI job names `python`, `integration`, `web`, `e2e` (required checks); env var `GAUNTLET_TEST_DATABASE_URL` / `TEST_DATABASE_URL` and `REDIS_URL` as the switch for integration tests.

**Decisions:**
- Marker plumbing in root `conftest.py`: a test marked `integration` is skipped with reason "needs compose services" unless `TEST_DATABASE_URL` is set; `chaos` additionally needs `GAUNTLET_CHAOS=1`; `live` needs `GAUNTLET_LIVE=1` (README testing rules). Unit gate must pass with no services running.
- `ci.yml` triggers: `push` to `main`, all `pull_request`. `concurrency: group: ci-${{ github.ref }}, cancel-in-progress: true`. `permissions: contents: read`. All jobs `ubuntu-latest`, `timeout-minutes: 20`.
- Job `python`: `actions/checkout`, `astral-sh/setup-uv` with cache keyed on `uv.lock`, `uv sync --all-packages --frozen`, then the four gate commands as separate steps (so the failing step is visible): `ruff check`, `ruff format --check`, `pyright packages`, `pytest packages -q`.
- Job `integration` (needs `python`): `services:` postgres `pgvector/pgvector:pg16` (health: `pg_isready`, interval 5 s, retries 10; env user `gauntlet`, password `gauntlet-dev-only`, db `gauntlet_test`; `CREATE EXTENSION vector` step via `psql` because service containers do not run init scripts) and redis `redis:7` (health `redis-cli ping`). MinIO is started in a step with `docker run -d -p 9000:9000 minio/minio server /data` (service containers cannot pass args). Env `TEST_DATABASE_URL`, `REDIS_URL`, `S3_*` point at localhost. Steps: if `packages/server/alembic.ini` exists run `uv run alembic -c packages/server/alembic.ini upgrade head` against the test database; then `uv run pytest tests/integration packages -q -m integration`. Use `if: hashFiles('tests/integration/**') != '' || ...` style guards so the job is green before P1-8 exists.
- Job `web`: guarded by `hashFiles('apps/web/package.json') != ''`; `pnpm/action-setup`, `actions/setup-node` (Node LTS, pnpm cache), `pnpm install --frozen-lockfile`, then `pnpm --filter web lint`, `typecheck`, `test`.
- Job `e2e`: only on `push` to `main` and on PRs labelled `e2e`; compose up with `--wait`, `uv run gauntlet demo seed`, `pnpm --filter web e2e`; upload `apps/web/test-results` and `apps/web/e2e/.screens` as artifacts on failure. Guard on `hashFiles('apps/web/package.json')`.
- `nightly.yml`: `schedule: cron '17 3 * * *'` plus `workflow_dispatch`: runs `tests/chaos` (`GAUNTLET_CHAOS=1`) against compose with `--scale worker=3`; `live` job exists but is `if: false` until a repo secret named `OPENROUTER_API_KEY` is set (documented in a comment; dollar cap env `GAUNTLET_LIVE_BUDGET_USD=2`).
- Pin third-party actions by major version tag (`@v4` etc.); look up the current majors (setup-uv, setup-node, pnpm/action-setup) instead of guessing. Never print secrets; no `pull_request_target`.
- `.pre-commit-config.yaml`: local hooks running `uv run ruff check --fix`, `uv run ruff format`, plus `check-yaml`, `end-of-file-fixer`, `trailing-whitespace` from `pre-commit-hooks`; pyright is not a hook (too slow).
- Package READMEs, 10 lines each: what it owns, what it must not import (`core` imports nothing from `server`/`cli`; `server` and `cli` import `core` only; `web` imports nothing outside `apps/web`).

**Steps:**
- [ ] Write `tests/test_marker_plumbing.py` using `pytester`-free approach: a tiny test module under `tests/_fixtures/` run with `pytest.main([...,'-p','no:cacheprovider'])` in a subprocess asserting: with `TEST_DATABASE_URL` unset an `integration` test is reported as skipped; with it set it runs. Run; fails.
- [ ] Implement `conftest.py` and markers; test passes.
- [ ] Write workflows, pre-commit, READMEs, pnpm/turbo files. Validate YAML with `uv run python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]" .github/workflows/*.yml` and, if available, `actionlint`.
- [ ] Push a branch and open a draft PR (only when the lead asks to push); confirm `python` and `integration` jobs are green and `web`/`e2e` are skipped.
- [ ] Gate **G**. Commit `ci: github actions, markers, pre-commit, package readmes`.

**Done when:** `G` green locally; the CI run on a throwaway branch shows `python` and `integration` green with web jobs skipped; `uv run pytest packages -q` passes with compose stopped.

---

## Contract questions (Phase 0)

| ID | Question |
|---|---|
| CQ-0.1 | The compose stack has no `web` or `dva` services. Proposal: P1-12 adds `web`, P1-11 adds `dva` under `profiles: ["dva"]` in the same compose file. Confirm. |
| CQ-0.2 | `GAUNTLET_ENV=dev` enables a fixed dev API key and unauthenticated `/openapi.json` (answers CQ-W6 and CQ-W7). Confirm that this dev-only behaviour is acceptable. |
