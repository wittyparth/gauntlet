"""The example script is part of the suite so it cannot rot."""

import importlib.util
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[4] / "examples" / "gateway" / "openai_tools.py"


def load():
    spec = importlib.util.spec_from_file_location("gateway_example", EXAMPLE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def test_example_blocks_in_enforce_and_only_logs_in_shadow():
    mod = load()
    shadow_answer, shadow = await mod.run("shadow")
    assert "refunded" in shadow_answer and "20000" in shadow_answer
    assert (shadow[0].action, shadow[0].would_have, shadow[0].enforced) == ("allow", "block", False)

    enforce_answer, enforce = await mod.run("enforce")
    assert "blocked_by_policy" in enforce_answer and "refunded" not in enforce_answer
    assert (enforce[0].action, enforce[0].would_have, enforce[0].rule_id) == (
        "block",
        None,
        "refund-cap",
    )
