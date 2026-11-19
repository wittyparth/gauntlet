from pathlib import Path

import pytest
from gauntlet_core.security.scan import LINT_RULES, lint_paths, lint_text

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "lint"


def hits(src: str, path: str = "x.py"):
    return [(f.rule_id, int(f.location.rsplit(":", 1)[1])) for f in lint_text(path, src)]


# (rule, bad source, expected line, good source)
CASES = {
    "LINT-001": (
        "@tool\ndef refund_order(order_id: str):\n    return order_id\n",
        2,
        "@tool\ndef refund_order(order_id: str, confirm: bool):\n    return order_id\n",
    ),
    "LINT-002": (
        'import os\nSYSTEM_PROMPT = "key is sk-abcdefghijklmnopqrstuvwxyz0123456789"\n',
        2,
        'SYSTEM_PROMPT = "no secrets here"\n',
    ),
    "LINT-003": (
        "def f(c, m):\n    while True:\n        c.chat.run(m)\n",
        2,
        "def f(c, m):\n    n = 0\n    while True:\n        c.chat.run(m)\n        n += 1\n"
        "        if n > 5:\n            break\n",
    ),
    "LINT-004": (
        "import requests\nrequests.get('http://x')\n",
        2,
        "import requests\nrequests.get('http://x', timeout=3)\n",
    ),
    "LINT-005": (
        "@tool\ndef sh(cmd: str):\n    return os.system(cmd)\n",
        3,
        "@tool\ndef sh(cmd: str):\n    return os.system('uptime')\n",
    ),
    "LINT-006": (
        "def f(q):\n    page = fetch_page(q)\n    return f'Answer from {page}'\n",
        3,
        "def f(q):\n    page = fetch_page(q)\n    return f'Answer from <page>{page}</page>'\n",
    ),
    "LINT-007": (
        "SCOPES = ['repo']\n",
        1,
        "SCOPES = ['repo:status']\n",
    ),
    "LINT-008": (
        "client.chat.completions.create(model='m', messages=[])\n",
        1,
        "client.chat.completions.create(model='m', messages=[], max_tokens=10)\n",
    ),
    "LINT-009": (
        "SYSTEM = '" + "You help with orders and shipping questions. " * 6 + "'\n",
        1,
        "SYSTEM = '" + "You help with orders. Decline anything else. " * 6 + "'\n",
    ),
    "LINT-010": (
        "def f(c):\n    out = c.chat.completions.create(model='m')\n    return eval(out)\n",
        3,
        "def f(c):\n    out = c.chat.completions.create(model='m', max_tokens=5)\n    return out\n",
    ),
    "LINT-011": (
        'AWS = "AKIAABCDEFGHIJKLMNOP"\n',
        1,
        'AWS = "not a key"\n',
    ),
}


@pytest.mark.parametrize("rule", sorted(CASES))
def test_bad_source_flags_exactly_the_rule_and_good_source_is_clean(rule):
    bad, line, good = CASES[rule]
    assert (rule, line) in hits(bad)
    assert {r for r, _ in hits(bad)} <= {rule, "LINT-008"}  # 010's call also lacks a cap
    assert hits(good) == []


def test_every_rule_has_a_case_and_catalogue_entry():
    assert set(CASES) == set(LINT_RULES)


def test_bad_fixture_has_at_least_six_rules_and_good_fixture_none():
    bad = lint_paths([FIX / "bad_agent.py"])
    assert len({f.rule_id for f in bad}) >= 6
    assert lint_paths([FIX / "good_agent.py"]) == []


def test_openai_format_tool_dicts_and_mcp_decorator():
    fn = "{'name': 'delete_all', 'description': 'x', 'parameters': {'properties': {}}}"
    d = f"T = {{'type': 'function', 'function': {fn}}}\n"
    assert hits(d) == [("LINT-001", 1)]
    assert hits("@mcp.tool()\ndef drop_table(name: str):\n    pass\n") == [("LINT-001", 2)]
    assert hits("@mcp.tool(require_approval=True)\ndef drop_table(name: str):\n    pass\n") == []


def test_pragma_suppresses_on_line_and_line_above(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("import requests\nrequests.get('x')  # gauntlet: ignore[LINT-004]\n")
    assert lint_paths([f]) == []
    f.write_text("import requests\n# gauntlet: ignore[LINT-004]\nrequests.get('x')\n")
    assert lint_paths([f]) == []
    f.write_text("import requests\n# gauntlet: ignore[LINT-001]\nrequests.get('x')\n")
    assert [x.rule_id for x in lint_paths([f])] == ["LINT-004"]


def test_select_and_ignore():
    path = FIX / "bad_agent.py"
    only = lint_paths([path], select=["LINT-004"])
    assert {f.rule_id for f in only} == {"LINT-004"}
    rest = lint_paths([path], ignore=["LINT-004"])
    assert "LINT-004" not in {f.rule_id for f in rest} and rest


def test_yaml_config_rules_007_011_and_001():
    got = {f.rule_id for f in lint_paths([FIX / "bad_config.yaml"])}
    assert got == {"LINT-007", "LINT-011", "LINT-001"}
    assert lint_paths([FIX / "good_config.yaml"]) == []
    # YAML findings carry the line
    assert all(
        f.location.rsplit(":", 1)[1].isdigit() for f in lint_paths([FIX / "bad_config.yaml"])
    )


def test_syntax_errors_are_not_findings():
    assert hits("def broken(:\n") == []
