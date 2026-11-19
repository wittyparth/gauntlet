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


async def test_invalid_structured_output_is_single_attempt_with_raw_text():
    """Recovery (repair + lenient) belongs to structured_call, so each retry is its own effect."""
    mock = AsyncMock(side_effect=[resp("not json"), resp('{"a": 2}')])
    with patch("litellm.acompletion", mock), pytest.raises(StructuredOutputError) as ei:
        await gw().complete("judge_small", MSGS, response_model=Out)
    assert ei.value.raw_text == "not json" and mock.await_count == 1


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


def resp_len(reasoning_tokens=480):
    msg = SimpleNamespace(content="", tool_calls=None)
    usage = SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=1024,
        completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning_tokens),
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=msg, finish_reason="length")], usage=usage
    )


async def _kwargs(role_cfg, role="judge_small", **kw):
    c = GatewayConfig()
    c.llm.roles[role] = role_cfg
    with patch("litellm.acompletion", AsyncMock(return_value=resp())) as m:
        await gw(c).complete(role, MSGS, **kw)
    return m.await_args_list[-1].kwargs


async def test_reasoning_off_is_passed_as_openrouter_extra_body():
    k = await _kwargs(RoleConfig(model="openrouter/qwen/qwen3.7-flash", reasoning="off"))
    assert k["extra_body"] == {"reasoning": {"enabled": False}}


@pytest.mark.parametrize("level", ["low", "medium", "high"])
async def test_reasoning_level_is_passed_as_effort(level):
    k = await _kwargs(RoleConfig(model="openrouter/qwen/qwen3.7-flash", reasoning=level))
    assert k["extra_body"] == {"reasoning": {"effort": level}}


async def test_reasoning_default_sends_nothing():
    k = await _kwargs(RoleConfig(model="openrouter/qwen/qwen3.7-flash", reasoning="default"))
    assert "extra_body" not in k


async def test_reasoning_not_sent_to_non_openrouter_models():
    k = await _kwargs(RoleConfig(model="p/other", reasoning="off"))
    assert "extra_body" not in k


async def test_model_roles_default_to_reasoning_off():
    c = GatewayConfig()
    with patch("litellm.acompletion", AsyncMock(return_value=resp())) as m:
        await gw(c).complete("model:openrouter/deepseek/deepseek-v4-flash", MSGS)
    assert m.await_args_list[-1].kwargs["extra_body"] == {"reasoning": {"enabled": False}}


async def test_empty_length_reply_raises_output_truncated_with_reasoning_tokens():
    from gauntlet_core.llm import OutputTruncated

    with (
        patch("litellm.acompletion", AsyncMock(return_value=resp_len(480))),
        pytest.raises(OutputTruncated) as ei,
    ):
        await gw().complete("judge_small", MSGS, response_model=Out)
    assert ei.value.code == "output_truncated" and "480" in ei.value.message


async def test_max_output_scale_doubles_max_tokens():
    c = GatewayConfig()
    c.llm.roles["judge_small"] = RoleConfig(model="p/x", max_output_tokens=1000)
    with patch("litellm.acompletion", AsyncMock(return_value=resp())) as m:
        await gw(c).complete("judge_small", MSGS, max_output_scale=2)
    assert m.await_args_list[-1].kwargs["max_tokens"] == 2000


async def test_reasoning_mandatory_400_retries_once_with_low_effort_and_double_budget(caplog):
    c = GatewayConfig()
    c.llm.roles["judge_strong"] = RoleConfig(
        model="openrouter/z-ai/glm-x", max_output_tokens=500, reasoning="off"
    )
    err = lx.BadRequestError(
        "Reasoning is mandatory for this endpoint and cannot be disabled.",
        llm_provider="openrouter",
        model="m",
    )
    with (
        patch("litellm.acompletion", AsyncMock(side_effect=[err, resp()])) as m,
        caplog.at_level("WARNING"),
    ):
        r = await gw(c).complete("judge_strong", MSGS)
    assert r.text == "ok" and m.await_count == 2
    first, second = (call.kwargs for call in m.await_args_list)
    assert first["extra_body"] == {"reasoning": {"enabled": False}} and first["max_tokens"] == 500
    assert second["extra_body"] == {"reasoning": {"effort": "low"}} and second["max_tokens"] == 1000
    assert "openrouter/z-ai/glm-x" in caplog.text


async def test_other_bad_requests_are_not_retried_with_reasoning():
    err = lx.BadRequestError("bad json", llm_provider="openrouter", model="m")
    with (
        patch("litellm.acompletion", AsyncMock(side_effect=err)) as m,
        pytest.raises(Exception, match="bad json"),
    ):
        await gw().complete("judge_small", MSGS)
    assert m.await_count == 1
