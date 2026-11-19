"""gauntlet.toml loading: role table, retry policy, rate limits, price overrides."""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Lead-pinned defaults (2026-11-19): cheap OpenRouter models only. The API key is read by
# litellm from OPENROUTER_API_KEY.
SMALL_MODEL = "openrouter/qwen/qwen3.7-flash"
STRONG_MODEL = "openrouter/z-ai/glm-5.3-flash"
ATTACKER_MODEL = "openrouter/deepseek/deepseek-v4-flash"
DEFAULT_MODEL = "openrouter/deepseek/deepseek-v4-flash"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoleConfig(Strict):
    model: str
    temperature: float | None = 0.0
    max_output_tokens: int = 1024
    fallbacks: list[str] = []


class RateLimitConfig(Strict):
    rpm: int = 60
    tpm: int = 100_000


class PricingConfig(Strict):
    input_per_mtok: int = 0  # usd micros per 1M tokens
    output_per_mtok: int = 0


def _default_roles() -> dict[str, RoleConfig]:
    return {
        "simulator": RoleConfig(model=SMALL_MODEL, temperature=0.7),
        "judge_small": RoleConfig(model=SMALL_MODEL, max_output_tokens=2048),
        "judge_strong": RoleConfig(model=STRONG_MODEL, max_output_tokens=2048),
        "attacker": RoleConfig(model=ATTACKER_MODEL, temperature=0.7),
        "generator": RoleConfig(model=DEFAULT_MODEL, temperature=0.7, max_output_tokens=4096),
        "embedder": RoleConfig(model="hash", temperature=None),
    }


def _default_pricing() -> dict[str, PricingConfig]:
    """usd micros per 1M tokens (in/out): qwen3.7-flash 0.03/0.13, glm-5.3-flash 0.15/0.50,
    deepseek-v4-flash 0.09/0.18 USD."""
    return {
        SMALL_MODEL: PricingConfig(input_per_mtok=30_000, output_per_mtok=130_000),
        STRONG_MODEL: PricingConfig(input_per_mtok=150_000, output_per_mtok=500_000),
        DEFAULT_MODEL: PricingConfig(input_per_mtok=90_000, output_per_mtok=180_000),
    }


class LlmSection(Strict):
    default_provider: str = "openrouter"
    request_timeout_s: float = 60
    max_attempts: int = 4
    backoff_base_s: float = 1.0
    rate_limits: dict[str, RateLimitConfig] = {}
    roles: dict[str, RoleConfig] = Field(default_factory=_default_roles)
    pricing: dict[str, PricingConfig] = Field(default_factory=_default_pricing)


class GatewayConfig(Strict):
    llm: LlmSection = Field(default_factory=LlmSection)


_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _interpolate(v: Any) -> Any:
    if isinstance(v, str):

        def sub(m: re.Match[str]) -> str:
            name = m.group(1)
            if name not in os.environ:
                raise ValueError(f"environment variable {name} is not set (used in config)")
            return os.environ[name]

        return _ENV.sub(sub, v)
    if isinstance(v, dict):
        return {k: _interpolate(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_interpolate(x) for x in v]
    return v


def load_config(path: Path | None = None) -> GatewayConfig:
    """Lookup order: explicit path, $GAUNTLET_CONFIG, ./gauntlet.toml, built-in defaults.
    Roles given in the file are merged over the built-in role table."""
    candidates = [path, Path(p) if (p := os.environ.get("GAUNTLET_CONFIG")) else None]
    candidates.append(Path("gauntlet.toml"))
    for c in candidates:
        if c is not None and c.is_file():
            data = _interpolate(tomllib.loads(c.read_text()))
            roles = data.get("llm", {}).get("roles")
            if roles is not None:
                merged = {k: v.model_dump() for k, v in _default_roles().items()}
                for name, r in roles.items():
                    merged[name] = {**merged.get(name, {}), **r}
                data["llm"]["roles"] = merged
            pricing = data.get("llm", {}).get("pricing")
            if pricing is not None:
                merged_p = {k: v.model_dump() for k, v in _default_pricing().items()}
                merged_p.update(pricing)
                data["llm"]["pricing"] = merged_p
            return GatewayConfig.model_validate(data)
    if path is not None:
        raise FileNotFoundError(path)
    return GatewayConfig()
