"""FastAPI app factory and process state construction (shared by api and worker)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import httpx
from fastapi import FastAPI
from gauntlet_core.llm import Gateway, GatewayConfig, LiteLLMGateway, load_config
from gauntlet_core.llm.scripted import load_scripted_llm
from redis import asyncio as aioredis

from .auth import ensure_default_workspace, upsert_key
from .config import Settings
from .db import make_engine, make_sessionmaker
from .deps import AppState
from .errors import ErrorEnvelope, install_errors
from .events import RedisPublisher
from .facade import router as facade_router
from .routes import (
    attacks,
    audit,
    badges,
    calibrations,
    cassettes,
    clusters,
    compare,
    core,
    dev,
    docs,
    findings,
    jobs,
    killswitch,
    migration,
    models,
    policies,
    posture,
    review,
    runs,
    scorecard,
    settings,
    stability,
    targets,
)
from .secrets import SecretStore

__all__ = ["app", "build_state", "create_app"]

log = logging.getLogger("gauntlet.app")


def _version() -> str:
    try:
        return version("gauntlet-server")
    except PackageNotFoundError:
        return "0.0.0"


def make_gateway(settings: Settings) -> tuple[Gateway, GatewayConfig]:
    path = Path(settings.config_path) if settings.config_path else None
    cfg = load_config(path if path is not None and path.is_file() else None)
    if settings.gateway.startswith("fake:"):
        if not settings.is_dev:
            raise RuntimeError("GAUNTLET_GATEWAY=fake:... is only allowed with GAUNTLET_ENV=dev")
        return load_scripted_llm(Path(settings.gateway[5:])), cfg
    return LiteLLMGateway(cfg), cfg


async def build_state(settings: Settings | None = None) -> AppState:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)
    sm = make_sessionmaker(engine)
    redis = aioredis.from_url(settings.redis_url)
    http = httpx.AsyncClient()
    gateway, cfg = make_gateway(settings)
    object_store = None
    if settings.s3_endpoint_url and settings.s3_bucket:
        from gauntlet_core.objectstore import S3ObjectStore

        object_store = S3ObjectStore(
            settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
            public_endpoint_url=settings.s3_public_endpoint_url or None,
        )
    state = AppState(
        object_store=object_store,
        settings=settings,
        sm=sm,
        gateway=gateway,
        gateway_config=cfg,
        secrets=SecretStore(sm, settings.fernet_key()),
        publisher=RedisPublisher(redis),
        redis=redis,
        http=http,
    )
    state.closers += [engine.dispose, http.aclose, redis.aclose]
    return state


def create_app(state: AppState | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        st = state or await build_state()
        app.state.gauntlet = st
        if st.settings.is_dev and st.settings.dev_api_key:
            async with st.sm() as s, s.begin():
                ws = await ensure_default_workspace(s)
                await upsert_key(s, ws, st.settings.dev_api_key, "dev")
        try:
            yield
        finally:
            if state is None:
                await st.aclose()

    dev_mode = state.settings.is_dev if state else Settings.from_env().is_dev
    application = FastAPI(
        title="Gauntlet",
        version=_version(),
        lifespan=lifespan,
        docs_url="/docs" if dev_mode else None,
        redoc_url=None,
        openapi_url="/openapi.json" if dev_mode else None,
        # core models carry a wrap serializer, so their serialization-mode schema is empty
        separate_input_output_schemas=False,
    )
    if state is not None:
        application.state.gauntlet = state
    install_errors(application)
    for r in (
        core.router, docs.router, runs.router, models.router, dev.router, facade_router,
        targets.router, audit.router, killswitch.router, settings.router,
        findings.router, attacks.router, posture.router, compare.router, stability.router,
        cassettes.router, jobs.router, review.router, calibrations.router, clusters.router,
        badges.router, badges.public, migration.router, scorecard.router, policies.router,
    ):  # fmt: skip
        application.include_router(r)

    @application.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": _version()}

    def openapi_with_envelope() -> dict:  # error envelope schema in the document
        from fastapi.openapi.utils import get_openapi

        if application.openapi_schema is None:
            schema = get_openapi(
                title=application.title,
                version=application.version,
                routes=application.routes,
                separate_input_output_schemas=False,
            )
            schema.setdefault("components", {}).setdefault("schemas", {})["ErrorEnvelope"] = (
                ErrorEnvelope.schema
            )
            application.openapi_schema = schema
        return application.openapi_schema

    application.openapi = openapi_with_envelope  # type: ignore[method-assign]
    return application


app = create_app()
