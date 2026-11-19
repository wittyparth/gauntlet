# One image definition for api and worker. Build context is the repo root.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=0 UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependency layer: only manifests, so code edits do not bust it.
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY packages/server/pyproject.toml packages/server/pyproject.toml
COPY packages/cli/pyproject.toml packages/cli/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package gauntlet-server
COPY packages/ packages/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package gauntlet-server

FROM python:3.12-slim-bookworm AS runtime
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd --uid 10001 --create-home gauntlet
WORKDIR /app
COPY --from=builder --chown=gauntlet:gauntlet /app/.venv /app/.venv
# Migrations and alembic.ini are not part of the wheel; the migrate service needs them.
COPY --chown=gauntlet:gauntlet packages/server/alembic.ini packages/server/alembic.ini
COPY --chown=gauntlet:gauntlet packages/server/migrations packages/server/migrations
COPY --chown=gauntlet:gauntlet packs/ ./packs/
COPY --chown=gauntlet:gauntlet attacks/ ./attacks/
USER gauntlet

FROM runtime AS api
EXPOSE 8000
CMD ["uvicorn", "gauntlet_server.app:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS worker
CMD ["python", "-m", "gauntlet_server.worker"]
