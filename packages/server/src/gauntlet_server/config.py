"""Process settings, read once from the environment (the same variables for api and worker)."""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field

__all__ = ["DEV_SECRET_SEED", "Settings"]

log = logging.getLogger("gauntlet.config")

# Dev without GAUNTLET_SECRET_KEY: a fixed key, so the api and the worker (separate
# processes) agree on it. Never used outside GAUNTLET_ENV=dev.
DEV_SECRET_SEED = b"gauntlet-dev-secret-key-not-for-production"


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    return int(env.get(name) or default)


@dataclass(frozen=True)
class Settings:
    env: str = "dev"
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    dev_api_key: str = ""
    secret_key: str = ""
    gateway: str = ""  # "" = LiteLLM; "fake:<path>" = scripted gateway (dev only)
    config_path: str | None = None
    public_api_url: str = "http://api:8000"
    max_run_budget_usd_micros: int = 50_000_000
    worker_concurrency: int = 4
    lease_s: int = 60
    poll_interval_s: float = 1.0
    allow_private_targets: bool = False
    verification_ttl_days: int = 90
    attacks_disabled: bool = False  # ops lever: reject every attack run at the API
    kill_poll_s: float = 1.0
    local_target_hosts: frozenset[str] = field(
        default_factory=lambda: frozenset({"dva", "dva-sql", "dva-email", "localhost", "127.0.0.1"})
    )

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        e = os.environ if env is None else env
        hosts = e.get("GAUNTLET_LOCAL_TARGET_HOSTS") or "dva,dva-sql,dva-email,localhost,127.0.0.1"
        return cls(
            env=e.get("GAUNTLET_ENV", "dev"),
            database_url=e.get("DATABASE_URL", ""),
            redis_url=e.get("REDIS_URL", "redis://localhost:6379/0"),
            dev_api_key=e.get("GAUNTLET_DEV_API_KEY", ""),
            secret_key=e.get("GAUNTLET_SECRET_KEY", ""),
            gateway=e.get("GAUNTLET_GATEWAY", ""),
            config_path=e.get("GAUNTLET_CONFIG") or None,
            public_api_url=e.get("GAUNTLET_PUBLIC_API_URL") or "http://api:8000",
            max_run_budget_usd_micros=_int(e, "GAUNTLET_MAX_RUN_BUDGET_USD_MICROS", 50_000_000),
            worker_concurrency=_int(e, "WORKER_CONCURRENCY", 4),
            lease_s=_int(e, "LEASE_SECONDS", 60),
            poll_interval_s=float(e.get("POLL_INTERVAL_S") or 1.0),
            allow_private_targets=(e.get("GAUNTLET_ALLOW_PRIVATE_TARGETS") or "").lower()
            in ("1", "true", "yes"),
            verification_ttl_days=_int(e, "GAUNTLET_VERIFICATION_TTL_DAYS", 90),
            attacks_disabled=(e.get("GAUNTLET_ATTACKS_DISABLED") or "").lower()
            in ("1", "true", "yes"),
            kill_poll_s=float(e.get("GAUNTLET_KILL_POLL_S") or 1.0),
            local_target_hosts=frozenset(h.strip() for h in hosts.split(",") if h.strip()),
        )

    def fernet_key(self) -> bytes:
        if self.secret_key:
            return self.secret_key.encode()
        if not self.is_dev:
            raise RuntimeError("GAUNTLET_SECRET_KEY is required outside GAUNTLET_ENV=dev")
        log.warning("GAUNTLET_SECRET_KEY is not set: using the fixed DEV key (dev mode only)")
        return base64.urlsafe_b64encode(hashlib.sha256(DEV_SECRET_SEED).digest())

    def mock_secret(self) -> bytes:
        """HMAC key for episode tokens of the mock facade: derived, so api and worker agree."""
        return hashlib.sha256(b"gauntlet-mock-v1:" + self.fernet_key()).digest()
