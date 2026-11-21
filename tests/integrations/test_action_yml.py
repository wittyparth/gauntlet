from pathlib import Path

import yaml

ACTION = Path(__file__).parents[2] / "integrations" / "github-action" / "action.yml"

DEFAULTS = {
    "repetitions": "1",
    "budget-usd": "2",
    "baseline-label": "main",
    "gates-file": "gauntlet-gates.yaml",
    "comment": "true",
    "sarif": "false",
}


def load() -> dict:
    return yaml.safe_load(ACTION.read_text())


def test_parses_as_a_composite_action():
    doc = load()
    assert doc["runs"]["using"] == "composite"
    assert doc["name"] and doc["description"]


def test_declares_the_specified_inputs_with_defaults():
    inputs = load()["inputs"]
    for name in ("api-url", "api-key", "suite", "agent-version"):
        assert inputs[name]["required"] is True
    for name, default in DEFAULTS.items():
        assert inputs[name]["default"] == default, name
    assert "baseline" in inputs and "cli-version" in inputs
    assert inputs["cli-version"]["default"] not in ("", "latest")  # pinned


def test_every_run_step_declares_its_shell():
    for step in load()["runs"]["steps"]:
        if "run" in step:
            assert step.get("shell"), step.get("name")


def test_secrets_only_reach_steps_through_env_and_are_never_echoed():
    text = ACTION.read_text()
    for step in load()["runs"]["steps"]:
        body = step.get("run", "")
        assert "inputs.api-key" not in body, step.get("name")
        assert "${{" not in body, step.get("name")  # expressions go through env, not the script
        for line in body.splitlines():
            if "echo" in line:
                assert "GAUNTLET_API_KEY" not in line
    uses_key = [
        s["name"] for s in load()["runs"]["steps"] if "inputs.api-key" in str(s.get("env", {}))
    ]
    assert uses_key  # the key is wired through env
    assert text.count("inputs.api-key") == len(uses_key)


def test_third_party_actions_are_pinned_to_a_major_tag():
    uses = [s["uses"] for s in load()["runs"]["steps"] if "uses" in s]
    assert {u.split("@")[0] for u in uses} == {
        "actions/setup-python",
        "actions/github-script",
        "github/codeql-action/upload-sarif",
    }
    for u in uses:
        tag = u.split("@")[1]
        assert tag.startswith("v") and tag[1:].isdigit(), u


def test_comment_only_on_same_repository_pull_requests():
    steps = {s["name"]: s for s in load()["runs"]["steps"] if "name" in s}
    cond = steps["Comment on the pull request"]["if"]
    assert "github.event_name == 'pull_request'" in cond
    assert "head.repo.full_name == github.repository" in cond
    assert "!= github.repository" in steps["Skip the comment on pull requests from forks"]["if"]


def test_final_step_mirrors_the_gate_exit_code():
    last = load()["runs"]["steps"][-1]
    assert last["if"] == "always()"
    assert 'exit "${GATE_EXIT}"' in last["run"]
