"""promptfoo importer: static `Prompt:` examples from `src/redteam/plugins/*.ts` in a checkout."""

from __future__ import annotations

import re
from pathlib import Path

from .common import Candidate, Skip, load_mapping

SOURCE = "promptfoo"
PLUGIN_DIR = Path("src/redteam/plugins")
_PROMPT_RE = re.compile(r"^\s*Prompt:\s*(.+?)\s*$")


def extract_examples(ts_source: str) -> list[str]:
    """`Prompt:` lines inside `<Example>` blocks (single line each)."""
    out: list[str] = []
    inside = False
    for line in ts_source.splitlines():
        if "<Example>" in line:
            inside = True
        elif "</Example>" in line:
            inside = False
        elif inside and (m := _PROMPT_RE.match(line)):
            out.append(m.group(1))
    return out


def read_candidates(src: Path) -> tuple[list[Candidate], list[Skip]]:
    m = load_mapping(SOURCE)
    cands: list[Candidate] = []
    skips: list[Skip] = []
    for name in m["exclude"]:
        skips.append(Skip(SOURCE, name, "excluded_plugin", "dangerous or out-of-scope subject"))
    for file_stem, spec in sorted(m["plugins"].items()):
        path = src / PLUGIN_DIR / f"{file_stem}.ts"
        if not path.is_file():
            skips.append(Skip(SOURCE, file_stem, "missing_file", str(path)))
            continue
        for i, text in enumerate(extract_examples(path.read_text())):
            for sub in m["substitutions"]:
                text = re.sub(sub["pattern"], sub["value"], text)
            cands.append(
                Candidate(
                    upstream_id=f"{spec['plugin']}#{i}",
                    title=f"promptfoo {spec['plugin']}",
                    category=spec["category"],
                    vector=spec["vector"],
                    technique=spec["technique"] + "; objective_source: substituted",
                    payload=text,
                    objective=spec["objective"],
                    requires=list(spec.get("requires", [])),
                    group=spec["plugin"],
                    cap=20,
                )
            )
    return cands, skips
