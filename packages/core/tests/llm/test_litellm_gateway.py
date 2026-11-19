import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import litellm.exceptions as lx
import pytest
from gauntlet_core.llm import (
    AuthError,
    GatewayConfig,
    LiteLLMGateway,
    PricingConfig,
    RoleConfig,
    StructuredOutputError,
)
from pydantic import BaseModel


class Out(BaseModel):
    a: int


def resp(content="ok", in_tok=1000, out_tok=100):
    msg = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=msg, finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=in_tok, completion_tokens=out_tok),
    )


def gw(config=None, sleeps=None):
    async def sleep(s):
        if sleeps is not None:
            sleeps.append(s)

    return LiteLLMGateway(config or GatewayConfig(), sleep=sleep, jitter=lambda: 1.0)


MSGS = [{"role": "user", "content": "hi"}]


async def test_retries_429_then_succeeds():
    sleeps: list[float] = []
    err = lx.RateLimitError("slow", llm_provider="openrouter", model="m")
    with patch("litellm.acompletion", AsyncMock(side_effect=[err, resp()])) as m:
        r = await gw(sleeps=sleeps).complete("judge_small", MSGS)
    assert r.text == "ok" and m.await_count == 2 and sleeps == [1.0]


async def test_does_not_retry_auth_error():
    err = lx.AuthenticationError("no", llm_provider="openrouter", model="m")
    with patch("litellm.acompletion", AsyncMock(side_effect=err)) as m, pytest.raises(AuthError):
        await gw().complete("judge_small", MSGS)
    assert m.await_count == 1


async def test_falls_back_after_primary_exhausted():
    c = GatewayConfig()
    c.llm.roles["judge_small"] = RoleConfig(model="p/primary", fallbacks=["p/backup"])
    c.llm.max_attempts = 2
    err = lx.ServiceUnavailableError("down", llm_provider="p", model="m")
    mock = AsyncMock(side_effect=[err, err, resp()])
    with patch("litellm.acompletion", mock):
        r = await gw(c).complete("judge_small", MSGS)
    assert [k.kwargs["model"] for k in mock.await_args_list] == ["p/primary"] * 2 + ["p/backup"]
    assert r.model == "p/backup"


async def test_structured_output_repair_sums_cost():
    mock = AsyncMock(side_effect=[resp("not json"), resp('{"a": 2}')])
    with patch("litellm.acompletion", mock):
        r = await gw().complete("judge_small", MSGS, response_model=Out)
    assert r.parsed == Out(a=2)
    assert r.cost.input_tokens == 2000
    second = mock.await_args_list[1].kwargs["messages"]
    assert second[-1]["content"].startswith("Your previous output was invalid")
    assert second[-2] == {"role": "assistant", "content": "not json"}
    # qwen3.7-flash: 1000 in * 0.03/M + 100 out * 0.13/M = 43 micros per call
    assert r.cost.usd_micros == 86


async def test_second_invalid_raises():
    mock = AsyncMock(side_effect=[resp("x"), resp("y")])
    with patch("litellm.acompletion", mock), pytest.raises(StructuredOutputError):
        await gw().complete("judge_small", MSGS, response_model=Out)


async def test_unpriced_model_recorded():
    g = gw()
    with (
        patch("litellm.acompletion", AsyncMock(return_value=resp())),
        patch("litellm.completion_cost", side_effect=Exception("no price")),
    ):
        r = await g.complete("model:p/mystery", MSGS)
    assert r.cost.usd_micros == 0 and "p/mystery" in g.unpriced_models


async def test_model_prefix_bypasses_role_lookup():
    mock = AsyncMock(return_value=resp())
    with patch("litellm.acompletion", mock):
        await gw().complete("model:openrouter/vendor/x", MSGS)
    assert mock.await_args is not None and mock.await_args.kwargs["model"] == "openrouter/vendor/x"


async def test_tool_calls_parsed():
    fn = SimpleNamespace(name="f", arguments=json.dumps({"x": 1}))
    tc = SimpleNamespace(id="c1", function=fn)
    r0 = resp()
    r0.choices[0].message.tool_calls = [tc]
    with patch("litellm.acompletion", AsyncMock(return_value=r0)):
        r = await gw().complete("judge_small", MSGS, tools=[{"type": "function"}])
    assert r.tool_calls[0].arguments == {"x": 1}


def test_estimate_uses_pricing_override():
    c = GatewayConfig()
    c.llm.pricing["p/x"] = PricingConfig(input_per_mtok=2_000_000, output_per_mtok=0)
    c.llm.roles["r"] = RoleConfig(model="p/x", max_output_tokens=10)
    assert gw(c).estimate_usd_micros("r", [{"role": "user", "content": "hello"}]) > 0
