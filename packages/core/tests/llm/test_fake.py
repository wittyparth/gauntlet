import pytest
from gauntlet_core.llm import FakeLLM, FakeReply, RateLimited
from pydantic import BaseModel


class Out(BaseModel):
    a: int


async def test_script_consumed_in_order():
    f = FakeLLM(["one", FakeReply(text="two"), lambda msgs: f"n={len(msgs)}"])
    assert (await f.complete("r", [])).text == "one"
    assert (await f.complete("r", [])).text == "two"
    assert (await f.complete("r", [{"role": "user", "content": "x"}])).text == "n=1"
    assert [c.role for c in f.calls] == ["r", "r", "r"]
    f.assert_consumed()


async def test_exhaustion_raises_with_call_number():
    f = FakeLLM(["only"])
    await f.complete("r", [])
    with pytest.raises(AssertionError, match="exhausted at call 1"):
        await f.complete("r", [])


async def test_by_role_scripts_are_independent():
    f = FakeLLM(["fallback"], by_role={"a": ["A1"], "b": ["B1"]})
    assert (await f.complete("b", [])).text == "B1"
    assert (await f.complete("a", [])).text == "A1"
    assert (await f.complete("other", [])).text == "fallback"
    f.assert_consumed()


async def test_dict_parsed_is_validated_into_model():
    f = FakeLLM([FakeReply(parsed={"a": 3})])
    r = await f.complete("r", [], response_model=Out)
    assert r.parsed == Out(a=3)


async def test_assert_consumed_fails_when_replies_remain():
    f = FakeLLM(["x", "y"])
    await f.complete("r", [])
    with pytest.raises(AssertionError):
        f.assert_consumed()


async def test_error_reply_raises_gateway_error():
    f = FakeLLM([FakeReply(error=RateLimited("slow"))])
    with pytest.raises(RateLimited):
        await f.complete("r", [])
