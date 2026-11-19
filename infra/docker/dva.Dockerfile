# The Damn Vulnerable Agent. INTENTIONALLY VULNERABLE: never expose it publicly.
# Build context is the repo root. Same multi-stage pattern as python.Dockerfile.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=0 UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY packages/server/pyproject.toml packages/server/pyproject.toml
COPY packages/cli/pyproject.toml packages/cli/pyproject.toml
COPY apps/dva/pyproject.toml apps/dva/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package gauntlet-dva
COPY packages/ packages/
COPY apps/dva/ apps/dva/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package gauntlet-dva

FROM python:3.12-slim-bookworm AS dva
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    DVA_HOST=0.0.0.0 DVA_PORT=8100 DVA_PACK_DIR=/app/packs/ecommerce
RUN useradd --uid 10001 --create-home gauntlet
WORKDIR /app
COPY --from=builder --chown=gauntlet:gauntlet /app/.venv /app/.venv
COPY --chown=gauntlet:gauntlet packs/ ./packs/
USER gauntlet
EXPOSE 8100
CMD ["python", "-m", "dva.app"]
