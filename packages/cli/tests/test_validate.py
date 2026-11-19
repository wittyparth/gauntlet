from __future__ import annotations

import json
import shutil
from pathlib import Path

from cli_helpers import FIXTURES, invoke


def test_clean_pack_exits_zero(runner, pack):
    res = invoke(runner, ["validate", str(pack)])
    assert res.exit_code == 0 and res.stdout == ""


def test_broken_tool_reference_exits_2_with_line_format(runner, pack, tmp_path: Path):
    copy = tmp_path / "tinyshop"
    shutil.copytree(pack, copy)
    scn = copy / "scenarios" / "scn_tiny_status.yaml"
    scn.write_text(scn.read_text().replace("tool: lookup_order", "tool: lookup_ordr"))
    res = invoke(runner, ["validate", str(copy)])
    assert res.exit_code == 2
    line = res.stdout.strip().splitlines()[0]
    path, code, message = line.split(":", 2)
    assert path.endswith("scenarios/scn_tiny_status.yaml") and code == "unknown_tool"
    assert "lookup_ordr" in message


def test_json_output_lists_issues(runner, pack, tmp_path: Path):
    copy = tmp_path / "tinyshop"
    shutil.copytree(pack, copy)
    scn = copy / "scenarios" / "scn_tiny_cancel.yaml"
    scn.write_text(
        scn.read_text().replace("rubrics: [task_completion, tone_empathy]", "rubrics: [nope]")
    )
    res = invoke(runner, ["validate", str(copy), "--json"])
    assert res.exit_code == 2
    issues = json.loads(res.stdout)
    assert [i["code"] for i in issues] == ["unknown_rubric"]


def test_unknown_persona_and_missing_world_are_pack_errors(runner, pack, tmp_path: Path):
    copy = tmp_path / "tinyshop"
    shutil.copytree(pack, copy)
    (copy / "pack.yaml").write_text(
        (copy / "pack.yaml").read_text().replace("[per_cooperative]", "[per_nobody]")
    )
    res = invoke(runner, ["validate", str(copy)])
    assert res.exit_code == 2 and "pack_error" in res.stdout and "per_nobody" in res.stdout


def test_scenario_file_is_validated_in_pack_context(runner, pack, tmp_path: Path):
    ok = invoke(runner, ["validate", str(pack / "scenarios" / "scn_tiny_status.yaml")])
    assert ok.exit_code == 0
    copy = tmp_path / "tinyshop"
    shutil.copytree(pack, copy)
    f = copy / "scenarios" / "scn_tiny_status.yaml"
    f.write_text(f.read_text().replace("tool: cancel_order", "tool: refund_everything"))
    bad = invoke(runner, ["validate", str(f)])
    assert bad.exit_code == 2 and "unknown_tool" in bad.stdout


def test_agent_file_and_garbage(runner, tmp_path: Path):
    assert invoke(runner, ["validate", str(FIXTURES / "agent.yaml")]).exit_code == 0
    bad = tmp_path / "agent.yaml"
    bad.write_text("label: x\ntarget: {kind: hosted}\n")
    res = invoke(runner, ["validate", str(bad)])
    assert res.exit_code == 2 and "schema" in res.stdout
    other = tmp_path / "x.yaml"
    other.write_text("hello: world\n")
    assert invoke(runner, ["validate", str(other)]).exit_code == 2
    assert invoke(runner, ["validate", str(tmp_path / "missing")]).exit_code == 2


def test_impure_handler_is_reported(runner, pack, tmp_path: Path):
    copy = tmp_path / "tinyshop"
    shutil.copytree(pack, copy)
    (copy / "impure_mod.py").write_text(
        "import itertools\nc = itertools.count()\n"
        "def handler(view, args, now):\n"
        "    from gauntlet_core.world import ToolOutcome\n"
        "    return ToolOutcome(result=next(c))\n"
    )
    import sys

    sys.path.insert(0, str(copy))
    try:
        world = copy / "world.yaml"
        world.write_text(
            world.read_text()
            + "  - name: bad_tool\n    description: impure\n    risk: read\n"
            + "    handler: {kind: python, entrypoint: 'impure_mod:handler'}\n"
        )
        res = invoke(runner, ["validate", str(copy)])
    finally:
        sys.path.remove(str(copy))
        sys.modules.pop("impure_mod", None)
    assert res.exit_code == 2 and "handler_impure" in res.stdout
