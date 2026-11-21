"""Finding exports: a gathered `Bundle`, then pure renderers for markdown, JSON and SARIF."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gauntlet_core.schema import Attack, Finding
from gauntlet_core.security import (
    SarifResult,
    SarifRule,
    Taxonomy,
    security_severity,
    to_sarif,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import models as m
from ..db.sec_models import Attack as AttackRow
from ..db.sec_models import Finding as FindingRow
from ..db.sec_models import FindingEpisode
from .findings import row_to_finding

__all__ = [
    "Bundle",
    "EpisodeEvidence",
    "gather_bundle",
    "render_json",
    "render_markdown",
    "render_sarif",
]

PAYLOAD_LIMIT = 500
_LEVEL = {"critical": "error", "high": "error", "medium": "warning", "low": "note"}


@dataclass
class EpisodeEvidence:
    episode_id: str
    role: str
    seqs: list[int]
    quotes: list[tuple[int, str]] = field(default_factory=list)
    causal_calls: list[str] = field(default_factory=list)


@dataclass
class Bundle:
    finding: Finding
    attack: Attack | None
    episodes: list[EpisodeEvidence]
    version_label: str
    status: str


async def gather_bundle(session: AsyncSession, row: FindingRow) -> Bundle:
    finding = row_to_finding(row)
    arow = await session.get(AttackRow, row.attack_id) if row.attack_id else None
    av = await session.get(m.AgentVersion, row.agent_version_id)
    links = (
        (
            await session.execute(
                select(FindingEpisode)
                .where(FindingEpisode.finding_id == row.id)
                .order_by(FindingEpisode.created_at, FindingEpisode.episode_id)
            )
        )
        .scalars()
        .all()
    )
    eps: list[EpisodeEvidence] = []
    for ln in links:
        ev = EpisodeEvidence(ln.episode_id, ln.role, list(ln.evidence_seqs or []))
        events = (
            (await session.execute(select(m.Event).where(m.Event.episode_id == ln.episode_id)))
            .scalars()
            .all()
        )
        by_seq = {e.seq: e for e in events}
        for e in events:
            if e.kind == "check_result" and e.doc.get("payload", {}).get("check_id") == "objective":
                for item in e.doc["payload"].get("evidence", []):
                    text = str(item.get("quote") or item.get("note") or "")
                    ev.quotes.append((int(item["seq"]), text[:300]))
        for q in ev.quotes:
            src = by_seq.get(q[0])
            if src is not None and src.kind == "tool_call":
                p = src.doc.get("payload", {})
                ev.causal_calls.append(f"{p.get('tool')}({', '.join(sorted(p.get('args', {})))})")
        eps.append(ev)
    return Bundle(
        finding,
        Attack.model_validate(arow.doc) if arow else None,
        eps,
        av.label if av else row.agent_version_id,
        row.status,
    )


def _owasp(tax: Taxonomy, category: str) -> str:
    cat = tax.get(category)
    return ", ".join(cat.owasp_llm) if cat and cat.owasp_llm else "none mapped"


def _payload_excerpt(b: Bundle) -> str:
    if b.attack is None:
        return ""
    text = b.attack.payload if isinstance(b.attack.payload, str) else "\n".join(b.attack.payload)
    return text[:PAYLOAD_LIMIT] + (" [truncated]" if len(text) > PAYLOAD_LIMIT else "")


def render_markdown(b: Bundle, tax: Taxonomy) -> str:
    f = b.finding
    ok, n = f.reproducibility
    lines = [
        f"# {f.title}",
        "",
        f"- Severity: **{f.severity}**",
        f"- Category: {f.category} (OWASP LLM: {_owasp(tax, f.category)})",
        f"- Status: {b.status}",
        f"- Agent version: {b.version_label}",
        f"- Reproducibility: {ok} of {n} attempts",
    ]
    if b.attack is not None:
        lines += [
            f"- Attack technique: {b.attack.technique}",
            f"- Source: {b.attack.source} (licence {b.attack.license})",
            f"- Vector: {b.attack.vector}",
        ]
    lines += ["", "## Reproducer", ""]
    excerpt = _payload_excerpt(b)
    if excerpt:
        lines += [
            "```text",
            excerpt,
            "```",
            "",
            "Dangerous-content categories are never stored; this payload is a placeholder-form "
            "excerpt of at most 500 characters.",
        ]
    else:
        lines.append(f"Pinned scenario `{f.reproducer.id}`.")
    lines += ["", "## Evidence", ""]
    if not b.episodes:
        lines.append("No episodes are linked.")
    for e in b.episodes:
        lines.append(f"- Episode `{e.episode_id}` ({e.role})")
        lines += [f"  - [{seq}] {quote}" for seq, quote in e.quotes]
    calls = sorted({c for e in b.episodes for c in e.causal_calls})
    if calls:
        lines += ["", "## Causal tool calls", ""] + [f"- {c}" for c in calls]
    if f.root_cause_hint:
        lines += ["", "## Root cause hint", "", f.root_cause_hint]
    if f.suggested_policy is not None:
        p = f.suggested_policy
        lines += ["", "## Suggested policy", "", f"- {p.id}: {p.description} ({p.action})"]
    return "\n".join(lines) + "\n"


def render_json(b: Bundle) -> dict[str, Any]:
    return {
        **b.finding.model_dump(mode="json"),
        "status": b.status,
        "episodes": [
            {"episode_id": e.episode_id, "role": e.role, "evidence_seqs": e.seqs}
            for e in b.episodes
        ],
    }


def render_sarif(bundles: list[Bundle], tax: Taxonomy, tool_version: str) -> dict[str, Any]:
    cats = sorted({b.finding.category for b in bundles})
    rules = []
    for c in cats:
        cat = tax.get(c)
        rules.append(
            SarifRule(
                id=c,
                name=cat.title if cat else c,
                short=cat.title if cat else c,
                full=cat.description if cat else "",
                tags=[*(cat.owasp_llm if cat else ()), "security"],
            )
        )
    results = []
    for b in bundles:
        f = b.finding
        calls = sorted({c.split("(")[0] for e in b.episodes for c in e.causal_calls})
        results.append(
            SarifResult(
                rule_id=f.category,
                level=_LEVEL[f.severity],  # type: ignore[arg-type]
                message=f"{f.title} ({f.reproducibility[0]} of {f.reproducibility[1]} attempts)",
                logical_locations=[b.version_label, *calls],
                fingerprint=f.dedup_key,
                properties={"security-severity": security_severity(f.severity)},
            )
        )
    return to_sarif("gauntlet", tool_version, rules, results)
