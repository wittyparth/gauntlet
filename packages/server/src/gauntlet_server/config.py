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
    daily_budget_usd_micros: int = 0  # 0 = no cap; else the sum of run budgets per rolling 24 h
    worker_concurrency: int = 4
    job_concurrency: int = 2
    drift_check: bool = False  # worker re-checks calibrations daily (P3-5)
    auto_cluster_min: int = 5  # failed episodes that trigger a cluster job (P3-6)
    cluster_embedder: str = "hash"  # "hash" (offline, free) or "gateway" (catalog model, opt-in)
    attribute_with_llm: bool = False  # root-cause fallback through judge_small
    max_fp_rate: float = 0.02  # enforce gate: offline-test false-positive rate (P4-5)
    min_block_rate: float = 0.5  # enforce gate: offline-test block rate
    prod_retention_days: int = 30  # production conversations (P5-1)
    ingest_max_spans: int = 5000
    ingest_max_bytes: int = 4 * 1024 * 1024
    ingest_sample_rate: float = 1.0
    ingest_rate_per_s: int = 50
    lease_s: int = 60
    poll_interval_s: float = 1.0
    allow_private_targets: bool = False
    verification_ttl_days: int = 90
    attacks_disabled: bool = False  # ops lever: reject every attack run at the API
    kill_poll_s: float = 1.0
    s3_endpoint_url: str = ""  # "" = no object store (cassette archive answers 503)
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_public_endpoint_url: str = ""  # the name browsers use for presigned urls
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
            daily_budget_usd_micros=round(
                float(e.get("GAUNTLET_DAILY_BUDGET_USD") or 0) * 1_000_000
            ),
            worker_concurrency=_int(e, "WORKER_CONCURRENCY", 4),
            job_concurrency=_int(e, "WORKER_JOB_CONCURRENCY", 2),
            drift_check=(e.get("GAUNTLET_DRIFT_CHECK") or "").lower() in ("1", "true", "yes"),
            auto_cluster_min=_int(e, "GAUNTLET_AUTO_CLUSTER_MIN", 5),
            cluster_embedder=e.get("GAUNTLET_CLUSTER_EMBEDDER") or "hash",
            attribute_with_llm=(e.get("GAUNTLET_ATTRIBUTE_WITH_LLM") or "false").lower()
            in ("1", "true", "yes"),
            max_fp_rate=float(e.get("GAUNTLET_MAX_FP_RATE") or 0.02),
            min_block_rate=float(e.get("GAUNTLET_MIN_BLOCK_RATE") or 0.5),
            prod_retention_days=_int(e, "GAUNTLET_PROD_RETENTION_DAYS", 30),
            ingest_max_spans=_int(e, "GAUNTLET_INGEST_MAX_SPANS", 5000),
            ingest_max_bytes=_int(e, "GAUNTLET_INGEST_MAX_BYTES", 4 * 1024 * 1024),
            ingest_sample_rate=float(e.get("GAUNTLET_INGEST_SAMPLE_RATE") or 1.0),
            ingest_rate_per_s=_int(e, "GAUNTLET_INGEST_RATE_PER_S", 50),
            lease_s=_int(e, "LEASE_SECONDS", 60),
            poll_interval_s=float(e.get("POLL_INTERVAL_S") or 1.0),
            allow_private_targets=(e.get("GAUNTLET_ALLOW_PRIVATE_TARGETS") or "").lower()
            in ("1", "true", "yes"),
            verification_ttl_days=_int(e, "GAUNTLET_VERIFICATION_TTL_DAYS", 90),
            attacks_disabled=(e.get("GAUNTLET_ATTACKS_DISABLED") or "").lower()
            in ("1", "true", "yes"),
            kill_poll_s=float(e.get("GAUNTLET_KILL_POLL_S") or 1.0),
            s3_endpoint_url=e.get("S3_ENDPOINT_URL", ""),
            s3_access_key=e.get("S3_ACCESS_KEY", ""),
            s3_secret_key=e.get("S3_SECRET_KEY", ""),
            s3_bucket=e.get("S3_BUCKET", ""),
            s3_region=e.get("S3_REGION") or "us-east-1",
            s3_public_endpoint_url=e.get("S3_PUBLIC_ENDPOINT_URL", ""),
            local_target_hosts=frozenset(h.strip() for h in hosts.split(",") if h.strip()),
        )

    def fernet_key(self) -> bytes:
        if self.secret_key:
            return self.secret_key.encode()
        if not self.is_dev:
            raise RuntimeError("GAUNTLET_SECRET_KEY is required outside GAUNTLET_ENV=dev")
        log.warning("GAUNTLET_SECRET_KEY is not set: using the fixed DEV key (dev mode only)")
        return base64.urlsafe_b64encode(hashlib.sha256(DEV_SECRET_SEED).digest())

    def redaction_key(self) -> bytes:
        """Keys the typed redaction tokens: stable across processes, not derivable from them."""
        return hashlib.sha256(b"gauntlet-redaction-v1:" + self.fernet_key()).digest()

    def mock_secret(self) -> bytes:
        """HMAC key for episode tokens of the mock facade: derived, so api and worker agree."""
        return hashlib.sha256(b"gauntlet-mock-v1:" + self.fernet_key()).digest()
