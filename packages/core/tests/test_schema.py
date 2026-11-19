import pytest
import yaml
from gauntlet_core.schema import Check, Matcher, Scenario, dump_yaml
from gauntlet_core.schema.checks import All, Not, ToolCalled
from pydantic import TypeAdapter, ValidationError

SCN = {
    "id": "scn_refund_late",
    "title": "Late refund",
    "goal": "Get a refund after the window",
    "persona": "per_sympathetic",
    "world": "ecommerce",
    "success": {
        "type": "all",
        "of": [
            {"type": "not", "check": {"type": "tool_called", "tool": "issue_refund"}},
            {"type": "output", "matcher": {"regex": "(?i)return window"}},
        ],
    },
    "forbidden": [
        {
            "id": "over_cap",
            "description": "refund above order total",
            "severity": "critical",
            "check": {
                "type": "tool_called",
                "tool": "issue_refund",
                "args": {"amount": {"ref": "world:orders/{args.order_id}/total", "ref_op": "gt"}},
            },
        }
    ],
}


def test_scenario_roundtrip_and_discrimination():
    s = Scenario.model_validate(SCN)
    assert isinstance(s.success, All)
    first = s.success.of[0]
    assert isinstance(first, Not)
    assert isinstance(first.check, ToolCalled)
    again = Scenario.model_validate(yaml.safe_load(dump_yaml(s)))
    assert again == s


def test_rejects_unknown_fields_and_bad_checks():
    with pytest.raises(ValidationError):
        Scenario.model_validate({**SCN, "bogus": 1})
    with pytest.raises(ValidationError):
        Matcher()
    with pytest.raises(ValidationError):  # state needs id or where
        TypeAdapter(Check).validate_python(
            {"type": "state", "collection": "c", "path": "x", "matcher": {"eq": 1}}
        )


def test_matcher_in_alias():
    assert Matcher.model_validate({"in": [1, 2]}).in_ == [1, 2]
