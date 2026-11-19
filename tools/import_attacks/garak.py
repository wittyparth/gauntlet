# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
"""garak importer. Run inside an isolated env: `uv run --with garak==<ver> ...`.

Only whitelisted probe classes are instantiated (mapping file). A probe's `prompts` list is read;
no model, generator or detector is ever run. Detector classes are only read for their
`substrings` attribute.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any

from .common import Candidate, Skip, load_mapping, load_objective_templates

SOURCE = "garak"
_ROGUE_RE = re.compile(r"(?:say|print)\s+\"(.+?)\"[:?.\s]*$", re.IGNORECASE | re.DOTALL)


def _objective(
    kind: str, spec: dict[str, Any], probe: Any, i: int, prompt: str
) -> dict[str, Any] | None:
    if kind == "rogue_regex":
        m = _ROGUE_RE.search(prompt)
        return {"type": "output", "matcher": {"contains": m.group(1)}} if m else None
    if kind == "detector":
        name = (
            getattr(probe, "primary_detector", None)
            or (getattr(probe, "recommended_detector", [None])[0])
        )
        if not name or "." not in name:
            return None
        mod, cls = name.split(".", 1)
        det = getattr(importlib.import_module(f"garak.detectors.{mod}"), cls)
        subs = list(getattr(det, "substrings", []))
        if not subs:
            return None
        return {"type": "any", "of": [{"type": "output", "matcher": {"contains": s}} for s in subs]}
    if kind == "trigger":
        triggers = getattr(probe, "triggers", None)
        if not triggers or len(triggers) != len(probe.prompts):
            return None
        t = triggers[i]
        t = t if isinstance(t, str) else (t[0] if t else "")
        allow = spec.get("trigger_allow")
        if allow and not re.search(allow, t):
            return None  # e.g. encoding probes also carry slur lists: only allow-listed triggers
        return {"type": "output", "matcher": {"contains": t}} if t else None
    if kind == "template":
        return load_objective_templates()[spec["template"]]  # type: ignore[no-any-return]
    if kind == "explicit":
        return dict(spec["check"])
    return None


def _last_user_turn(conv: Any) -> str | None:
    """The final user turn of a garak `Conversation` (the attack text; the system turn is the
    probe's stand-in target prompt and is not imported)."""
    turns = getattr(conv, "turns", None) or []
    if not turns or getattr(turns[-1], "role", "") != "user":
        return None
    return str(turns[-1].content.text)


def read_candidates(
    _src: Path | None = None, *, max_per_probe: int = 5
) -> tuple[list[Candidate], list[Skip]]:
    from garak import _config

    _config.load_base_config()
    m = load_mapping(SOURCE)
    cands: list[Candidate] = []
    skips: list[Skip] = []
    for name in m["exclude_classes"]:
        skips.append(Skip(SOURCE, name, "excluded_class", "dangerous or out-of-scope subject"))
    for full, spec in sorted(m["classes"].items()):
        mod, cls = full.split(".", 1)
        if mod in m["exclude_modules"] or full in m["exclude_classes"]:
            skips.append(Skip(SOURCE, full, "excluded_module", mod))
            continue
        probe = getattr(importlib.import_module(f"garak.probes.{mod}"), cls)()
        for i, prompt in enumerate(probe.prompts):
            if spec.get("payload") == "last_user_turn" and not isinstance(prompt, str):
                prompt = _last_user_turn(prompt)
            if not isinstance(prompt, str):
                skips.append(Skip(SOURCE, f"{full}#{i}", "non_text_prompt"))
                continue
            for old, new in m["substitutions"].items():
                prompt = prompt.replace(old, new)
            obj = _objective(spec["objective"], spec, probe, i, prompt)
            if obj is None:
                skips.append(Skip(SOURCE, f"{full}#{i}", "no_objective_or_trigger_not_allowed"))
                continue
            tech = spec.get("technique") or f"encoding:{cls.removeprefix('Inject').lower()}"
            cands.append(
                Candidate(
                    upstream_id=f"{full}#{i}",
                    title=f"garak {full}",
                    category=spec["category"],
                    vector=spec["vector"],
                    technique=tech,
                    payload=prompt,
                    objective=obj,
                    requires=list(spec.get("requires", [])),
                    group=full,
                    cap=int(spec.get("cap", max_per_probe)),
                )
            )
    return cands, skips
