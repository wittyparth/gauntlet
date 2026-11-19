"""Shared normalisation, safety filtering, dedupe and output for the attack importers.

No payload text is written here: importers read upstream data and this module only cleans,
filters and stores it.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from gauntlet_core.schema import Attack
from gauntlet_core.security import Taxonomy, load_taxonomy, validate_attack

__all__ = [
    "CATEGORY_CAP",
    "SOURCE_PRIORITY",
    "Candidate",
    "Skip",
    "build_attacks",
    "dangerous_reason",
    "existing_hashes",
    "load_mapping",
    "load_objective_templates",
    "normalise_payload",
    "payload_hash",
    "summarise_skips",
    "unresolved_template",
    "update_skipped",
    "write_library",
]

MAX_CHARS = 4000
CATEGORY_CAP = 40
SOURCE_PRIORITY = ("agentdojo", "injecagent", "garak", "promptfoo")
REPO_ROOT = Path(__file__).resolve().parents[2]
MAPPINGS = Path(__file__).parent / "mappings"

# Subjects that are never imported (CQ-S7, phase safety rules). A payload or objective trigger
# that matches is skipped and counted in skipped.json; the filter is deliberately broad.
_DANGEROUS = {
    "weapons": r"\b(bombs?|explosives?|detonat\w*|bioweapons?|chemical weapons?|nerve agents?|"
    r"anthrax|ricin|napalm|molotov|firearms?|ammunition|grenades?|nuclear weapons?|"
    r"dirty bomb|weapons? of mass)\b",
    "malware": r"\b(ransomware|malware|keylogger|botnet|rootkit|computer virus|trojan|"
    r"spyware|credential stealer)\b",
    "self_harm": r"\b(suicide|self[- ]harm|kill (yourself|myself)|overdose|eating disorder|"
    r"anorexi\w*)\b",
    "csam": r"\b(csam|child (porn\w*|sexual\w*|abuse)|minors? (nude|sexual)|underage sex\w*)\b",
    "violence_hate": r"\b(kill (all )?humans|genocide|ethnic cleansing|terroris[mt]\w*|"
    r"hate speech|racial slurs?|discriminatory)\b|\bslurs?\b|\bgay men\b",
    "illegal_drugs": r"\b(synthesi[sz]e (meth|fentanyl)|cook(ing)? meth|crack cocaine)\b",
    "sexual": r"\b(porn\w*|explicit sexual|erotic)\b",
    "deepfake_crime": r"\b(deepfake|crime scene|alibi)\b",
}
_DANGEROUS_RE = {k: re.compile(v, re.IGNORECASE) for k, v in _DANGEROUS.items()}
_TEMPLATE_RE = re.compile(
    r"\{\{|\{[A-Za-z_][\w. ]*\}|\[(?:INSERT|INSERT [A-Za-z ]+|PLACEHOLDER)\]", re.IGNORECASE
)
_NEWLINES_RE = re.compile(r"\n{3,}")


@dataclass
class Candidate:
    """One attack as read from an upstream source, before normalisation."""

    upstream_id: str
    title: str
    category: str
    vector: str
    technique: str
    payload: str
    objective: dict[str, Any]
    requires: list[str] = field(default_factory=list)
    severity: str | None = None
    group: str = ""  # sampling group (probe, plugin, suite); the per-probe cap applies per group
    cap: int | None = None  # per-group cap override (defaults to max_per_group)


@dataclass
class Skip:
    source: str
    upstream_id: str
    reason: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "id": self.upstream_id,
            "reason": self.reason,
            "detail": self.detail,
        }


def normalise_payload(text: str) -> str | None:
    """NFC, strip, collapse 3+ newlines to 2. None when empty or over the length cap."""
    out = _NEWLINES_RE.sub("\n\n", unicodedata.normalize("NFC", text).strip())
    if not out or len(out) > MAX_CHARS:
        return None
    return out


def payload_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def unresolved_template(text: str) -> str | None:
    m = _TEMPLATE_RE.search(_strip_allowed(text))
    return m.group(0) if m else None


_ALLOWED_RE = re.compile(
    r"\{\{\s*(?:marker|attacker_email|attacker_url|honeytool|user_goal|canary:[\w.-]+)\s*\}\}"
)


def _strip_allowed(text: str) -> str:
    return _ALLOWED_RE.sub("", text)


def dangerous_reason(*texts: str) -> str | None:
    """Name of the first dangerous-content class that any of the texts matches."""
    for t in texts:
        for name, rx in _DANGEROUS_RE.items():
            if rx.search(t):
                return name
    return None


def load_mapping(source: str) -> dict[str, Any]:
    data = yaml.safe_load((MAPPINGS / f"{source}.yaml").read_text())
    assert isinstance(data, dict)
    return data


def load_objective_templates() -> dict[str, Any]:
    data = yaml.safe_load((REPO_ROOT / "attacks" / "objectives.yaml").read_text())
    assert isinstance(data, dict)
    return data


def _strings(obj: Any) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _sample(
    items: list[tuple[Candidate, str]], cap: int, rng: random.Random
) -> tuple[list[tuple[Candidate, str]], list[tuple[Candidate, str]]]:
    if len(items) <= cap:
        return items, []
    keep = set(rng.sample(range(len(items)), cap))
    return (
        [x for i, x in enumerate(items) if i in keep],
        [x for i, x in enumerate(items) if i not in keep],
    )


def build_attacks(
    cands: Sequence[Candidate],
    *,
    source: str,
    project: str,
    pin: str,
    license_id: str,
    severities: dict[str, str],
    taxonomy: Taxonomy | None = None,
    seed: int = 0,
    max_per_group: int = 5,
    category_cap: int = CATEGORY_CAP,
    seen_hashes: set[str] | None = None,
) -> tuple[list[Attack], list[Skip]]:
    """Filter, dedupe and sample candidates into valid `Attack`s (deterministic for a seed)."""
    tax = taxonomy or load_taxonomy()
    seen = seen_hashes if seen_hashes is not None else set()
    skips: list[Skip] = []
    ok: list[tuple[Candidate, str]] = []
    for c in sorted(cands, key=lambda c: c.upstream_id):
        text = normalise_payload(c.payload)
        if text is None:
            skips.append(Skip(source, c.upstream_id, "empty_or_too_long"))
            continue
        bad = unresolved_template(text)
        if bad:
            skips.append(Skip(source, c.upstream_id, "unresolved_template", bad))
            continue
        danger = dangerous_reason(text, *_strings(c.objective))
        if danger:
            skips.append(Skip(source, c.upstream_id, "dangerous_content", danger))
            continue
        h = payload_hash(text)
        if h in seen:
            skips.append(Skip(source, c.upstream_id, "duplicate", h[:8]))
            continue
        seen.add(h)
        ok.append((c, text))
    rng = random.Random(seed)
    groups: dict[str, list[tuple[Candidate, str]]] = defaultdict(list)
    for item in ok:
        groups[item[0].group or item[0].upstream_id].append(item)
    picked: list[tuple[Candidate, str]] = []
    for key in sorted(groups):
        keep, drop = _sample(groups[key], groups[key][0][0].cap or max_per_group, rng)
        skips += [Skip(source, c.upstream_id, "over_probe_cap", key) for c, _ in drop]
        picked += keep
    by_cat: dict[str, list[tuple[Candidate, str]]] = defaultdict(list)
    for item in picked:
        by_cat[item[0].category].append(item)
    attacks: list[Attack] = []
    for cat in sorted(by_cat):
        keep, drop = _sample(by_cat[cat], category_cap, rng)
        skips += [Skip(source, c.upstream_id, "over_category_cap", cat) for c, _ in drop]
        for c, text in keep:
            a = Attack.model_validate(
                {
                    "id": f"atk_{source}_{payload_hash(text)[:8]}",
                    "title": c.title,
                    "category": c.category,
                    "technique": c.technique,
                    "source": f"{project}@{pin}:{c.upstream_id}",
                    "license": license_id,
                    "vector": c.vector,
                    "payload": text,
                    "objective": c.objective,
                    "requires": c.requires,
                    "severity": c.severity or severities[c.category],
                }
            )
            issues = validate_attack(a, tax)
            if issues:
                skips.append(Skip(source, c.upstream_id, "invalid", str(issues[0])))
                continue
            attacks.append(a)
    return sorted(attacks, key=lambda a: a.id), skips


def write_library(attacks: Sequence[Attack], out_dir: Path, source: str) -> None:
    """Write `<out_dir>/<source>/<category>.yaml` (replacing that source's files)."""
    src_dir = out_dir / source
    if src_dir.exists():
        for f in src_dir.glob("*.yaml"):
            f.unlink()
    src_dir.mkdir(parents=True, exist_ok=True)
    by_cat: dict[str, list[Attack]] = defaultdict(list)
    for a in attacks:
        by_cat[a.category].append(a)
    for cat, items in by_cat.items():
        rows = [a.model_dump(mode="json", by_alias=True, exclude_unset=True) for a in items]
        (src_dir / f"{cat}.yaml").write_text(
            yaml.safe_dump(rows, sort_keys=False, allow_unicode=True, width=100)
        )


def existing_hashes(out_dir: Path, higher: Iterable[str]) -> set[str]:
    """Payload hashes already in the library from higher-priority sources."""
    out: set[str] = set()
    for src in higher:
        src_dir = out_dir / src
        for f in sorted(src_dir.glob("*.yaml")) if src_dir.is_dir() else []:
            for row in yaml.safe_load(f.read_text()) or []:
                payload = row["payload"]
                out.add(payload_hash(payload if isinstance(payload, str) else "\n".join(payload)))
    return out


LISTED_REASONS = (
    "dangerous_content",
    "excluded_class",
    "excluded_module",
    "excluded_plugin",
    "excluded_type",
    "invalid",
    "missing_file",
    "upstream_tool_name",
)


def summarise_skips(skips: Sequence[Skip]) -> dict[str, Any]:
    """Counts per reason, every safety or invalid skip listed individually, and the rest
    (sampling, dedupe, template and objective gaps) counted per upstream probe or group."""
    counts: dict[str, int] = {}
    by_group: dict[str, dict[str, int]] = {}
    for s in skips:
        counts[s.reason] = counts.get(s.reason, 0) + 1
        if s.reason not in LISTED_REASONS:
            group = (s.detail if s.reason.startswith("over_") else s.upstream_id).split("#")[0]
            row = by_group.setdefault(s.reason, {})
            row[group] = row.get(group, 0) + 1
    return {
        "counts": dict(sorted(counts.items())),
        "by_group": {k: dict(sorted(v.items())) for k, v in sorted(by_group.items())},
        "entries": [s.as_dict() for s in skips if s.reason in LISTED_REASONS],
    }


def update_skipped(out_dir: Path, source: str, skips: Sequence[Skip]) -> None:
    path = out_dir / "skipped.json"
    data: dict[str, Any] = json.loads(path.read_text()) if path.is_file() else {}
    data[source] = summarise_skips(skips)
    path.write_text(json.dumps(dict(sorted(data.items())), indent=1, ensure_ascii=False) + "\n")
