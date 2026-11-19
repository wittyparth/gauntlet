"""Curated model catalog: the cheap non-frontier models customers may pick per role.

Ids, prices, context lengths and reasoning capabilities were read on 2026-11-19 from the public
`https://openrouter.ai/api/v1/models` listing (`pricing`, `context_length`, `reasoning.mandatory`,
`supported_parameters` containing `tools` and `response_format`). Every entry accepts tool calls
and JSON output, and none has mandatory reasoning, so `reasoning = "off"` is valid for all.
Never add OpenAI or Anthropic models (project decision).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from .config import GatewayConfig, PricingConfig, Reasoning

__all__ = [
    "CATALOG",
    "SETTABLE_ROLES",
    "CatalogModel",
    "RoleChoice",
    "apply_role_settings",
    "catalog_model",
]

SETTABLE_ROLES = ("simulator", "judge_small", "judge_strong", "attacker", "generator")


class CatalogModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    provider_family: str
    input_usd_per_mtok: float
    output_usd_per_mtok: float
    context_length: int
    supports_reasoning_off: bool
    reasoning_default: Literal["on", "off"]  # what the provider does when nothing is sent
    good_for: list[str]
    description: str
    recommended_roles: list[str]


class RoleChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    reasoning: Reasoning = "off"


CATALOG: list[CatalogModel] = [
    CatalogModel(
        id="openrouter/qwen/qwen3.7-flash",
        name="Qwen3.7 Flash",
        provider_family="Qwen",
        input_usd_per_mtok=0.03,
        output_usd_per_mtok=0.13,
        context_length=1_000_000,
        supports_reasoning_off=True,
        reasoning_default="on",
        good_for=["user simulation", "judging", "tool calling"],
        description="The cheapest capable model: fast, follows JSON schemas well. "
        "Thinks by default, so keep reasoning off.",
        recommended_roles=["simulator", "judge_small"],
    ),
    CatalogModel(
        id="openrouter/qwen/qwen3.8-flash",
        name="Qwen3.8 Flash",
        provider_family="Qwen",
        input_usd_per_mtok=0.15,
        output_usd_per_mtok=0.47,
        context_length=1_000_000,
        supports_reasoning_off=True,
        reasoning_default="on",
        good_for=["judging", "tool calling", "long context"],
        description="A stronger Qwen flash model with a 1M context; a good step up for judging.",
        recommended_roles=["judge_strong"],
    ),
    CatalogModel(
        id="openrouter/deepseek/deepseek-v4-flash",
        name="DeepSeek V4 Flash",
        provider_family="DeepSeek",
        input_usd_per_mtok=0.09,
        output_usd_per_mtok=0.18,
        context_length=1_048_576,
        supports_reasoning_off=True,
        reasoning_default="on",
        good_for=["attacks", "scenario generation", "tool calling"],
        description="Inventive and cheap, with reliable tool calling. "
        "Suited to adversarial probing and writing scenarios.",
        recommended_roles=["attacker", "generator"],
    ),
    CatalogModel(
        id="openrouter/google/gemini-2.5-flash-lite",
        name="Gemini 2.5 Flash Lite",
        provider_family="Google",
        input_usd_per_mtok=0.10,
        output_usd_per_mtok=0.40,
        context_length=1_048_576,
        supports_reasoning_off=True,
        reasoning_default="off",
        good_for=["judging", "structured output", "tool calling"],
        description="Steady structured output and a different model family from the "
        "simulator, which makes it a good second judge.",
        recommended_roles=["judge_strong", "judge_small"],
    ),
    CatalogModel(
        id="openrouter/mistralai/mistral-small-2603",
        name="Mistral Small 4",
        provider_family="Mistral",
        input_usd_per_mtok=0.15,
        output_usd_per_mtok=0.60,
        context_length=262_144,
        supports_reasoning_off=True,
        reasoning_default="off",
        good_for=["user simulation", "tool calling", "multilingual"],
        description="Natural conversational tone and sound tool calling; "
        "a good simulator for non-English personas.",
        recommended_roles=["simulator"],
    ),
    CatalogModel(
        id="openrouter/nvidia/nemotron-3-super-120b-a12b",
        name="Nemotron 3 Super",
        provider_family="NVIDIA",
        input_usd_per_mtok=0.075,
        output_usd_per_mtok=0.40,
        context_length=262_144,
        supports_reasoning_off=True,
        reasoning_default="on",
        good_for=["attacks", "judging", "tool calling"],
        description="A large open model at a low price; "
        "worth trying for attacks and as an independent judge.",
        recommended_roles=["attacker", "judge_strong"],
    ),
    CatalogModel(
        id="openrouter/google/gemma-4-31b-it",
        name="Gemma 4 31B",
        provider_family="Google",
        input_usd_per_mtok=0.20,
        output_usd_per_mtok=0.40,
        context_length=262_144,
        supports_reasoning_off=True,
        reasoning_default="off",
        good_for=["user simulation", "judging"],
        description="Compact open model without hidden reasoning by default; "
        "predictable latency and cost.",
        recommended_roles=["simulator", "judge_small"],
    ),
]

_BY_ID = {m.id: m for m in CATALOG}


def catalog_model(model_id: str) -> CatalogModel | None:
    return _BY_ID.get(model_id)


def apply_role_settings(config: GatewayConfig, settings: dict[str, RoleChoice]) -> GatewayConfig:
    """A copy of `config` with the chosen model and reasoning set on each role, and catalog
    prices added for models the config does not price. Precedence is therefore workspace
    setting over `gauntlet.toml` over built-in defaults."""
    out = config.model_copy(deep=True)
    for role, choice in settings.items():
        if role not in SETTABLE_ROLES:
            raise ValueError(f"role {role!r} cannot be configured")
        out.llm.roles[role] = out.llm.roles[role].model_copy(
            update={"model": choice.model, "reasoning": choice.reasoning}
        )
        cm = catalog_model(choice.model)
        if cm is not None and choice.model not in out.llm.pricing:
            out.llm.pricing[choice.model] = PricingConfig(
                input_per_mtok=round(cm.input_usd_per_mtok * 1_000_000),
                output_per_mtok=round(cm.output_usd_per_mtok * 1_000_000),
            )
    return out
