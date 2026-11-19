"""Per-run model roles: a gateway view that resolves roles from the run's recorded settings."""

from __future__ import annotations

from typing import Any

from gauntlet_core.llm import Gateway, LiteLLMGateway
from gauntlet_core.llm.catalog import RoleChoice, apply_role_settings

__all__ = ["gateway_for_roles"]


def gateway_for_roles(gateway: Gateway, roles: dict[str, Any] | None) -> Gateway:
    """The gateway that serves a run whose resolved role settings are `roles`
    ({role: {model, reasoning}}). It shares the process-wide rate limiter. Scripted and fake
    gateways (dev and tests) and runs without settings keep the gateway as it is."""
    if not roles or not isinstance(gateway, LiteLLMGateway):
        return gateway
    choices = {r: RoleChoice.model_validate(c) for r, c in roles.items()}
    return LiteLLMGateway(apply_role_settings(gateway.config, choices), limiter=gateway.limiter)
