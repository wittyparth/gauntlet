"""Arena settings, read once from the environment. Everything is off or capped by default."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

__all__ = ["ArenaSettings"]


def _int(e: Mapping[str, str], name: str, default: int) -> int:
    return int(e.get(name) or default)


@dataclass(frozen=True)
class ArenaSettings:
    enabled: bool = False  # ARENA_ENABLED: the arena answers 503 until the lead turns it on
    database_url: str = ""  # ARENA_DATABASE_URL: its own setting, may point at the platform DB
    redis_url: str = "redis://localhost:6379/0"
    secret: str = ""  # ARENA_SECRET: HMAC key of the per-attempt canaries
    retention_days: int = 14
    brain: str = "llm"  # "llm" (cheap catalog model) or "scripted" (no model, no cost)
    classifier: str = "fake"  # "fake" (deterministic heuristics) or "model" (the extra)
    daily_budget_usd_micros: int = 5_000_000
    ip_per_minute: int = 60
    handle_msgs_per_minute: int = 12
    attempts_per_handle_per_day: int = 20
    open_attempts_per_handle: int = 3
    max_turns: int = 20
    max_message_chars: int = 500
    max_tokens_per_attempt: int = 20_000
    attempt_ttl_s: int = 1800
    idle_s: int = 600
    trust_proxy: bool = False  # read the client address from X-Forwarded-For

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ArenaSettings:
        e = os.environ if env is None else env
        return cls(
            enabled=(e.get("ARENA_ENABLED", "false").lower() in ("1", "true", "yes")),
            database_url=e.get("ARENA_DATABASE_URL", ""),
            redis_url=e.get("ARENA_REDIS_URL") or e.get("REDIS_URL", "redis://localhost:6379/0"),
            secret=e.get("ARENA_SECRET", ""),
            retention_days=_int(e, "ARENA_RETENTION_DAYS", 14),
            brain=e.get("ARENA_BRAIN", "llm"),
            classifier=e.get("ARENA_CLASSIFIER", "fake"),
            daily_budget_usd_micros=_int(e, "ARENA_DAILY_BUDGET_USD_MICROS", 5_000_000),
            ip_per_minute=_int(e, "ARENA_IP_PER_MINUTE", 60),
            handle_msgs_per_minute=_int(e, "ARENA_HANDLE_MSGS_PER_MINUTE", 12),
            attempts_per_handle_per_day=_int(e, "ARENA_ATTEMPTS_PER_HANDLE_PER_DAY", 20),
            open_attempts_per_handle=_int(e, "ARENA_OPEN_ATTEMPTS_PER_HANDLE", 3),
            max_turns=_int(e, "ARENA_MAX_TURNS", 20),
            max_message_chars=_int(e, "ARENA_MAX_MESSAGE_CHARS", 500),
            max_tokens_per_attempt=_int(e, "ARENA_MAX_TOKENS_PER_ATTEMPT", 20_000),
            attempt_ttl_s=_int(e, "ARENA_ATTEMPT_TTL_S", 1800),
            idle_s=_int(e, "ARENA_IDLE_S", 600),
            trust_proxy=e.get("ARENA_TRUST_PROXY", "false").lower() in ("1", "true", "yes"),
        )
