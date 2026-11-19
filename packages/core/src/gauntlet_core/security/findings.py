"""Findings: creation, dedup and verification (hard-cores 6.6).

Dedup key = sha256 of (agent version, category, objective check hash, vector). A second success
of the same kind against the same agent version attaches its episode to the existing finding
(raising severity if the new causal chain is worse) instead of creating another.
`verify` re-runs the pinned reproducer; zero successes marks the finding `verified`."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from gauntlet_core.schema import (
    SEVERITY_ORDER,
    Attack,
    Event,
    Finding,
    Scenario,
    Severity,
    WorldSpec,
)

from .episodes import AttackOracle, ScenarioRunner
from .objectives import AttemptResult, bump_severity, check_hash
from .placement import place
from .shrink import ShrinkConfig, ShrinkResult, shrink_attack

__all__ = [
    "Filing",
    "FindingStore",
    "MemoryFindingStore",
    "VerifyResult",
    "dedup_key",
    "file_finding",
    "file_forbidden_findings",
    "verify",
]


DEFAULT_SHRINK = ShrinkConfig()


class FindingStore(Protocol):
    async def get_by_dedup(self, key: str) -> Finding | None: ...
    async def get(self, finding_id: str) -> Finding | None: ...
    async def put(self, finding: Finding) -> None: ...
    async def list(self) -> list[Finding]: ...


class MemoryFindingStore:
    def __init__(self) -> None:
        self._by_id: dict[str, Finding] = {}

    async def get_by_dedup(self, key: str) -> Finding | None:
        return next((f for f in self._by_id.values() if f.dedup_key == key), None)

    async def get(self, finding_id: str) -> Finding | None:
        return self._by_id.get(finding_id)

    async def put(self, finding: Finding) -> None:
        self._by_id[finding.id] = finding

    async def list(self) -> list[Finding]:
        return list(self._by_id.values())


def _digest(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def dedup_key(agent_version_id: str, attack: Attack) -> str:
    return _digest(agent_version_id, attack.category, check_hash(attack.objective), attack.vector)


def _max_sev(a: Severity, b: Severity) -> Severity:
    return a if SEVERITY_ORDER[a] >= SEVERITY_ORDER[b] else b


@dataclass(frozen=True)
class Filing:
    finding: Finding
    created: bool
    shrink: ShrinkResult | None = None


async def file_finding(
    store: FindingStore,
    attack: Attack,
    result: AttemptResult,
    *,
    agent_version_id: str,
    world: WorldSpec,
    scenario: Scenario,
    oracle: AttackOracle,
    shrink_id: str,
    seed: int = 0,
    config: ShrinkConfig | None = DEFAULT_SHRINK,
) -> Filing:
    """Record a successful attack. New key: shrink it, pin the reproducer, create the
    finding. Known key: attach the episode and keep the higher severity (no shrinking).
    `config=None` skips shrinking (the original attack is pinned with reproducibility 1/1)."""
    if not result.objective_held:
        raise ValueError("file_finding needs an attempt whose objective held")
    key = dedup_key(agent_version_id, attack)
    severity = bump_severity(attack.severity, result.causal_risks)
    existing = await store.get_by_dedup(key)
    if existing is not None:
        episodes = list(existing.episode_ids)
        if result.episode_id not in episodes:
            episodes.append(result.episode_id)
        updated = existing.model_copy(
            update={"episode_ids": episodes, "severity": _max_sev(existing.severity, severity)}
        )
        await store.put(updated)
        return Filing(updated, created=False)

    doc_body = None
    if attack.vector == "document":
        doc = next((d for d in world.documents if d.id == attack.target), None)
        doc = doc or (world.documents[0] if world.documents else None)
        doc_body = doc.body if doc else None
    pinned, repro, sr = attack, (1, 1), None
    if config is not None:
        sr = await shrink_attack(
            attack,
            oracle,
            base_id=shrink_id,
            config=config,
            doc_body=doc_body,
            world_doc=attack.target if doc_body is not None else None,
        )
        pinned, repro, doc_body = sr.attack, sr.reproducibility, sr.doc_body
    placed = place(pinned, world, scenario, seed=seed, doc_body=doc_body)
    finding = Finding(
        id=f"fnd_{key[:20]}",
        title=attack.title,
        category=attack.category,
        severity=severity,
        agent_version_id=agent_version_id,
        attack_id=attack.id,
        episode_ids=[result.episode_id],
        reproducibility=repro,
        reproducer=placed.scenario,
        dedup_key=key,
    )
    await store.put(finding)
    return Filing(finding, created=True, shrink=sr)


async def file_forbidden_findings(
    store: FindingStore,
    scenario: Scenario,
    events: Sequence[Event],
    *,
    agent_version_id: str,
    episode_id: str,
) -> list[Filing]:
    """A `critical` forbidden check that held also creates a finding (6.6). Category comes from
    `scenario.tags["category"]`; the pinned reproducer is the scenario itself (1 of 1)."""
    out: list[Filing] = []
    named = {n.id: n for n in scenario.forbidden}
    for e in events:
        if e.kind != "check_result" or not e.payload.get("holds"):
            continue
        n = named.get(e.payload["check_id"])
        if n is None or n.id == "objective" or n.severity != "critical":
            continue
        category = scenario.tags.get("category", "policy_violation")
        key = _digest(agent_version_id, category, check_hash(n.check), "scenario")
        existing = await store.get_by_dedup(key)
        if existing is not None:
            eps = [*existing.episode_ids, episode_id]
            updated = existing.model_copy(update={"episode_ids": list(dict.fromkeys(eps))})
            await store.put(updated)
            out.append(Filing(updated, created=False))
            continue
        finding = Finding(
            id=f"fnd_{key[:20]}",
            title=n.description,
            category=category,
            severity="critical",
            agent_version_id=agent_version_id,
            episode_ids=[episode_id],
            reproducibility=(1, 1),
            reproducer=scenario,
            dedup_key=key,
        )
        await store.put(finding)
        out.append(Filing(finding, created=True))
    return out


@dataclass(frozen=True)
class VerifyResult:
    finding: Finding
    successes: int
    attempts: int

    @property
    def verified(self) -> bool:
        return self.successes == 0


async def verify(
    finding: Finding,
    runner: ScenarioRunner,
    store: FindingStore | None = None,
    *,
    verify_id: str,
) -> VerifyResult:
    """Re-run the pinned reproducer `reproducibility[1]` times (at least once) against the
    agent version `runner` is bound to. Zero successes flips the status to `verified`; any
    success leaves it unchanged."""
    world = finding.reproducer.world
    if not isinstance(world, WorldSpec):
        raise ValueError(f"finding {finding.id}: reproducer must carry an inline placed world")
    attempts = max(1, finding.reproducibility[1])
    successes = 0
    for i in range(attempts):
        res = await runner(finding.reproducer, world, f"{verify_id}:{i}")
        successes += res.objective_held
    updated = finding if successes else finding.model_copy(update={"status": "verified"})
    if store is not None and updated is not finding:
        await store.put(updated)
    return VerifyResult(updated, successes, attempts)
