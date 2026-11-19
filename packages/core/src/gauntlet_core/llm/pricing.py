"""Cost arithmetic in integer usd micros."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gauntlet_core.schema import Cost

from .config import PricingConfig

SAFETY = 1.1


def cost_from_pricing(price: PricingConfig, input_tokens: int, output_tokens: int) -> int:
    return round(
        (input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok) / 1e6
    )


def to_micros(usd: float) -> int:
    return round(usd * 1_000_000)


def make_cost(model: str, usd_micros: int, input_tokens: int, output_tokens: int) -> Cost:
    return Cost(
        usd_micros=usd_micros, input_tokens=input_tokens, output_tokens=output_tokens, model=model
    )


def estimate_micros(
    pricing: Mapping[str, PricingConfig],
    model: str,
    input_tokens: int,
    max_output_tokens: int,
    litellm_prices: tuple[float, float] | None = None,
) -> int:
    """Input tokens at the input price plus the full output allowance at the output price,
    times a 1.1 safety factor. `litellm_prices` are (usd per input token, usd per output token)."""
    if model in pricing:
        base = cost_from_pricing(pricing[model], input_tokens, max_output_tokens)
    elif litellm_prices is not None:
        base = to_micros(input_tokens * litellm_prices[0] + max_output_tokens * litellm_prices[1])
    else:
        return 0
    return int(base * SAFETY + 0.999999)


def litellm_token_prices(model: str) -> tuple[float, float] | None:
    try:
        import litellm

        info: Any = litellm.model_cost.get(model.split("/", 1)[-1]) or litellm.model_cost.get(model)
        if not info:
            return None
        return float(info["input_cost_per_token"]), float(info["output_cost_per_token"])
    except Exception:
        return None
