import string

from check_helpers import Tb
from gauntlet_core.judges import (
    JudgeOutput,
    build_messages,
    normalize_text,
    render_trajectory,
    validate_evidence,
)
from gauntlet_core.judges.render import TOOL_RESULT_MAX, event_texts
from gauntlet_core.schema import RubricExample
from hypothesis import given
from hypothesis import strategies as st
from judge_helpers import QUOTE, rubric, traj


def out(result, evidence=(), conf=0.9):
    return JudgeOutput.model_validate(
        {
            "reasoning": "r",
            "evidence": [{"seq": s, "quote": q} for s, q in evidence],
            "result": result,
            "confidence": conf,
        }
    )


def test_rendering_has_seq_prefix_and_hides_simulator_internals():
    t = (
        Tb()
        .user("hi there")
        .agent("hello")
        .call("get_order", {"id": 1}, result={"total": 5})
        .build()
    )
    text = render_trajectory(t)
    assert text.splitlines()[0] == "[1] USER: hi there"
    assert "[3] TOOL_CALL: get_order" in text and "[4] TOOL_RESULT: ok:" in text
    msgs = build_messages(rubric(), t, policy_text="refunds need approval")
    assert "refunds need approval" in msgs[1]["content"]
    assert "persona" not in msgs[1]["content"].lower()
    assert msgs[0]["role"] == "system"


def test_tool_result_truncated_head_and_tail_kept():
    big = "HEAD" + "x" * 5000 + "TAIL"
    t = Tb().call("fetch", {}, result=big).build()
    body = event_texts(t)[2]
    assert len(body) < TOOL_RESULT_MAX + 100
    assert "HEAD" in body and "TAIL" in body and "truncated" in body


def test_at_most_four_examples_rendered():
    ex = [RubricExample(transcript=f"T{i}", result="pass", why="w") for i in range(6)]
    text = build_messages(rubric(examples=ex), traj())[1]["content"]
    assert "Example 4" in text and "Example 5" not in text


def test_valid_evidence_accepted_with_normalisation():
    t = event_texts(traj())
    assert validate_evidence(out("fail", [(2, QUOTE)]), t) == []
    assert validate_evidence(out("fail", [(2, "REFUNDED   order 42\nin FULL")]), t) == []
    assert validate_evidence(out("fail", [(2, "Sure, I have refunded")]), t) == []


def test_invalid_evidence_cases():
    t = event_texts(traj())
    assert validate_evidence(out("fail", [(99, QUOTE)]), t)  # unknown seq
    assert validate_evidence(out("fail", [(1, QUOTE)]), t)  # quote in the wrong event
    assert validate_evidence(out("fail", [(2, "refunded")]), t)  # too short
    assert validate_evidence(out("fail", [(2, "never said this at all")]), t)
    assert validate_evidence(out("fail"), t)  # fail needs evidence
    assert validate_evidence(out("pass", [(2, "invented quote text here")]), t)
    assert validate_evidence(out("pass"), t) == []  # empty pass is fine
    assert validate_evidence(out("na"), t, na_allowed=False)


@given(st.text(max_size=300), st.text(max_size=60))
def test_never_accepts_quote_absent_from_event(body, quote):
    o = out("pass", [(1, quote)])
    if validate_evidence(o, {1: body}) == []:
        assert normalize_text(quote) in normalize_text(body)
        assert len(normalize_text(quote)) >= 12


@given(st.text(alphabet=string.printable, min_size=20, max_size=300), st.data())
def test_verbatim_slices_are_accepted(body, data):
    i = data.draw(st.integers(0, len(body) - 12))
    j = data.draw(st.integers(i + 12, len(body)))
    quote = body[i:j]
    if len(normalize_text(quote)) >= 12:
        assert validate_evidence(out("pass", [(1, quote)]), {1: body}) == []
