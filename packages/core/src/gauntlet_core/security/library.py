"""Attack library: YAML lists of `Attack` under `attacks/library/<source>/<category>.yaml`."""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError

from gauntlet_core.schema import SEVERITY_ORDER, Attack
from gauntlet_core.validate import walk_check

from .placeholders import extract_placeholders, is_allowed_placeholder
from .taxonomy import Taxonomy

__all__ = [
    "CAPABILITIES",
    "ID_RE",
    "MAX_PAYLOAD_CHARS",
    "AttackLibrary",
    "Issue",
    "load_attacks",
    "payload_texts",
    "validate_attack",
]

ID_RE = re.compile(r"^atk_[a-z0-9_]{3,40}$")
MAX_PAYLOAD_CHARS = 4000
CAPABILITIES = frozenset(
    {
        "tool:read",
        "tool:write",
        "tool:destructive",
        "tool:financial",
        "tool:external_comm",
        "tool:honeytool",
        "documents",
        "untrusted_tool_output",
        "system_prompt_canary",
        "multi_turn",
        "sql_tool",
        "mcp",
    }
)


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    attack_id: str | None = None
    path: str | None = None

    def __str__(self) -> str:
        where = f"{self.path}: " if self.path else ""
        who = f"[{self.attack_id}] " if self.attack_id else ""
        return f"{where}{who}{self.code}: {self.message}"


def payload_texts(attack: Attack) -> list[str]:
    return [attack.payload] if isinstance(attack.payload, str) else list(attack.payload)


def validate_attack(attack: Attack, taxonomy: Taxonomy) -> list[Issue]:
    aid = attack.id
    out: list[Issue] = []

    def add(code: str, msg: str) -> None:
        out.append(Issue(code, msg, aid))

    if not ID_RE.match(aid):
        add("bad_id", f"id must match {ID_RE.pattern}")
    cat = taxonomy.get(attack.category)
    if cat is None:
        add("unknown_category", f"{attack.category!r} is not in the taxonomy")
    elif cat.dangerous:
        add("dangerous_category", f"category {cat.id} is never imported")
    if not attack.source.strip():
        add("missing_source", "source is empty")
    if not attack.license.strip():
        add("missing_license", "license is empty")
    texts = payload_texts(attack)
    if not texts or any(not t.strip() for t in texts):
        add("empty_payload", "payload is empty")
    placeholders: set[str] = set()
    for t in texts:
        if len(t) > MAX_PAYLOAD_CHARS:
            add("payload_too_long", f"a payload part has {len(t)} characters")
        placeholders.update(extract_placeholders(t))
    for p in sorted(placeholders):
        if not is_allowed_placeholder(p):
            add("unknown_placeholder", f"{{{{{p}}}}} is not an allowed placeholder")
    for r in attack.requires:
        if r not in CAPABILITIES:
            add("unknown_requires", f"{r!r} is not a known capability")
    if isinstance(attack.payload, list) and "multi_turn" not in attack.requires:
        add("list_needs_multi_turn", "a list payload requires multi_turn")
    if attack.vector == "document" and "documents" not in attack.requires:
        add("document_needs_documents", "vector document requires documents")
    if attack.vector == "tool_result" and "untrusted_tool_output" not in attack.requires:
        add("tool_result_needs_untrusted", "vector tool_result requires untrusted_tool_output")
    nodes = list(walk_check(attack.objective))
    if any(n.type == "judge" for n in nodes) and SEVERITY_ORDER[attack.severity] >= 2:
        add("judge_objective_high", "a judge objective is only allowed below severity high")
    for n in nodes:
        if (
            n.type == "canary_leaked"
            and n.canary != "*"
            and f"canary:{n.canary}" not in placeholders
        ):
            add("canary_unreferenced", f"canary {n.canary!r} is not referenced by the payload")
    return out


@dataclass
class AttackLibrary:
    attacks: list[Attack]
    issues: list[Issue] = field(default_factory=list)

    def all(self) -> list[Attack]:
        return list(self.attacks)

    def get(self, attack_id: str) -> Attack | None:
        return next((a for a in self.attacks if a.id == attack_id), None)

    def filter(
        self,
        category: str | None = None,
        vector: str | None = None,
        source: str | None = None,
        available: Collection[str] | None = None,
        q: str | None = None,
    ) -> list[Attack]:
        out = []
        for a in self.attacks:
            if category and a.category != category:
                continue
            if vector and a.vector != vector:
                continue
            if source and not a.source.startswith(source):
                continue
            if available is not None and not set(a.requires) <= set(available):
                continue
            hay = f"{a.title} {a.technique} {' '.join(payload_texts(a))}".lower()
            if q and q.lower() not in hay:
                continue
            out.append(a)
        return out

    def stats(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for a in self.attacks:
            row = out.setdefault(a.category, {})
            row[a.vector] = row.get(a.vector, 0) + 1
        return out


def _files(root: Path) -> Iterable[Path]:
    return sorted([*root.rglob("*.yaml"), *root.rglob("*.yml")]) if root.is_dir() else []


def load_attacks(root: Path, taxonomy: Taxonomy) -> AttackLibrary:
    """Load and validate every `*.yaml` under `root`. Problems are collected in `.issues`
    (parse errors, rule violations, duplicate ids); attacks that parse are still returned."""
    lib = AttackLibrary([])
    seen: dict[str, Path] = {}
    for f in _files(Path(root)):
        rel = str(f.relative_to(root))
        try:
            data = yaml.safe_load(f.read_text()) or []
            if not isinstance(data, list):
                raise ValueError("file must be a YAML list of attacks")
            attacks = [Attack.model_validate(d) for d in data]
        except (yaml.YAMLError, ValidationError, ValueError) as e:
            lib.issues.append(Issue("invalid_file", str(e).splitlines()[0], path=rel))
            continue
        for a in attacks:
            if a.id in seen:
                lib.issues.append(
                    Issue("duplicate_id", f"also defined in {seen[a.id].name}", a.id, rel)
                )
                continue
            seen[a.id] = f
            lib.issues.extend(
                Issue(i.code, i.message, i.attack_id, rel) for i in validate_attack(a, taxonomy)
            )
            lib.attacks.append(a)
    return lib
