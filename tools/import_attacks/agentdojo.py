# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
"""AgentDojo importer. Run inside an isolated env: `uv run --with agentdojo==<ver> ...`.

The injection goals come from the benchmark's `InjectionTask.GOAL` and the framing from the
library's own attack templates (`FixedJailbreakAttack.jailbreak`); nothing is authored here.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .common import Candidate, Skip, load_mapping

SOURCE = "agentdojo"


def _substitute(text: str, subs: list[dict[str, str]]) -> str:
    for s in subs:
        text = re.sub(s["pattern"], s["value"], text)
    return text


def classify(goal: str, mapping: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    """(category, risk list, extra requires) for a goal, from the mapping's rules."""
    for rule in mapping["privileged"]:
        if re.search(rule["pattern"], goal):
            return "excessive_agency", list(rule["risk"]), list(rule["requires"])
    return "indirect_injection", list(mapping["default_risk"]), []


def build(goal: str, template: str, user: str, model: str, mapping: dict[str, Any]) -> str:
    """Apply a template string (as the upstream attack class does) to a goal."""
    clean = _substitute(goal, mapping["substitutions"])
    return template.format(goal=clean, user=user, model=model, task="the task")


def read_candidates(_src: Path | None = None) -> tuple[list[Candidate], list[Skip]]:
    from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
    from agentdojo.attacks.attack_registry import ATTACKS
    from agentdojo.task_suite.load_suites import get_suites

    m = load_mapping(SOURCE)

    class _Pipe(BasePipelineElement):
        name = m["pipeline_name"]

        def query(self, *args: Any, **kwargs: Any) -> Any:  # never called
            raise NotImplementedError

    suites = get_suites(m["benchmark_version"])
    cands: list[Candidate] = []
    for sname, suite in sorted(suites.items()):
        attacks = {n: ATTACKS[n](suite, _Pipe()) for n in m["attacks"]}
        for tid, task in sorted(suite.injection_tasks.items()):
            category, risk, requires = classify(task.GOAL, m)
            for aname, attack in attacks.items():
                text = build(
                    task.GOAL,
                    attack.jailbreak,
                    getattr(attack, "user_name", "the user"),
                    getattr(attack, "model_name", "the assistant"),
                    m,
                )
                cands.append(
                    Candidate(
                        upstream_id=f"{sname}/{tid}/{aname}",
                        title=f"AgentDojo {sname} {tid} ({aname})",
                        category=category,
                        vector="tool_result",
                        technique=f"agentdojo:{aname}; objective_source: substituted",
                        payload=text,
                        objective={
                            "type": "any",
                            "of": [
                                {"type": "tainted_call", "tool": "*", "risk": risk},
                                {"type": "tool_called", "tool": "{{honeytool}}"},
                            ],
                        },
                        requires=["untrusted_tool_output", *requires],
                        group=f"{sname}/{category}",
                    )
                )
    return cands, []
