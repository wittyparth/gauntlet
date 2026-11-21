"""`gateway.yaml` for the MCP gateway (P4-3). Unknown keys are rejected."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = ["RISK_ORDER", "McpGatewayConfig", "ScanConfig", "ScopesConfig", "ServerConfig"]

RISK_ORDER = ["read", "write", "destructive", "financial", "external_comm"]
Risk = Literal["read", "write", "destructive", "financial", "external_comm"]
_NAME = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScopesConfig(_Strict):
    max_risk: Risk | None = None  # tools above this are hidden


class ScanConfig(_Strict):
    block_at: Literal["low", "medium", "high", "critical"] = "high"


def interpolate(value: str, environ: Mapping[str, str]) -> str:
    """`${NAME}` from `environ`; a missing variable is an error (never an empty secret)."""

    def sub(m: re.Match[str]) -> str:
        if m.group(1) not in environ:
            raise ValueError(f"environment variable {m.group(1)} is not set")
        return environ[m.group(1)]

    return _VAR.sub(sub, value)


class ServerConfig(_Strict):
    name: str
    transport: Literal["stdio", "http"]
    command: list[str] | None = None
    env: dict[str, str] = {}
    url: str | None = None
    headers: dict[str, str] = {}
    trust: Literal["trusted", "untrusted"] = "untrusted"
    allow_tools: list[str] = []
    deny_tools: list[str] = []
    scopes: ScopesConfig = ScopesConfig()

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not _NAME.match(v):
            raise ValueError("server name must match ^[a-z][a-z0-9_]{0,30}$")
        return v

    @model_validator(mode="after")
    def _transport_fields(self) -> ServerConfig:
        if self.transport == "stdio" and not self.command:
            raise ValueError(f"server {self.name}: stdio needs `command`")
        if self.transport == "http" and not self.url:
            raise ValueError(f"server {self.name}: http needs `url`")
        return self

    def resolved_env(self, environ: Mapping[str, str] | None = None) -> dict[str, str]:
        """Only these variables (plus PATH) reach a stdio server."""
        src = os.environ if environ is None else environ
        out = {"PATH": src.get("PATH", "")}
        out.update({k: interpolate(v, src) for k, v in self.env.items()})
        return out

    def resolved_headers(self, environ: Mapping[str, str] | None = None) -> dict[str, str]:
        src = os.environ if environ is None else environ
        return {k: interpolate(v, src) for k, v in self.headers.items()}


class McpGatewayConfig(_Strict):
    policy: str | None = None
    pins: str = "pins.json"
    on_pin_mismatch: Literal["block", "warn"] = "block"
    on_unpinned: Literal["block", "warn"] = "block"
    scan: ScanConfig = ScanConfig()
    risk_overrides: dict[str, Risk] = {}
    mode: Literal["shadow", "enforce"] | None = None
    servers: list[ServerConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> McpGatewayConfig:
        names = [s.name for s in self.servers]
        if len(set(names)) != len(names):
            raise ValueError("server names must be unique")
        return self

    @classmethod
    def load(cls, path: str | Path) -> McpGatewayConfig:
        """Relative `policy` and `pins` paths are resolved against the config file."""
        p = Path(path)
        cfg = cls.model_validate(yaml.safe_load(p.read_text()) or {})
        updates: dict[str, str | None] = {"pins": str(p.parent / cfg.pins)}
        if cfg.policy:
            updates["policy"] = str(p.parent / cfg.policy)
        return cfg.model_copy(update=updates)

    def server(self, name: str) -> ServerConfig:
        return next(s for s in self.servers if s.name == name)
