"""Evidence packs (P5-7): a signed, verifiable zip of the facts behind a release decision.

Wording is "evidence supporting", never "compliant". Contents: manifest, run manifests and run
reports, the posture report, coverage mapped to OWASP LLM and agentic ids (and an own-words
NIST AI RMF map; ISO/IEC text is never quoted), calibration results, policy versions and
gateway decision summaries, an audit-log excerpt with the hash-chain verification, cassette
references, `SHA256SUMS` and, when `GAUNTLET_EVIDENCE_SIGNING_KEY` is set, an Ed25519
`SIGNATURE`. Without the key the pack is built unsigned and flagged as such (CQ-P10).

Before zipping every JSON and text file passes the redaction of P1-4 and then a detector scan
(secrets and personal data); attack payload text is never included (ids only). A scan hit fails
the pack: the row records which file, never the matched text. The audit excerpt is not
redacted (it would break the hash chain); its rows carry ids, counts and hosts by rule, and it
is scanned for secrets only. Packs cost no model calls."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from gauntlet_core.checks.detectors.pii import detect_pii
from gauntlet_core.checks.detectors.secret import detect_secret
from gauntlet_core.evidence import AUDIT_EXCERPT, build_zip, public_key_b64
from gauntlet_core.ids import new_id
from gauntlet_core.ingest.redact import Redactor
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import models as m
from ..db.ops_models import EvidencePack
from ..db.policy_models import GatewayDecisionRow, PolicyVersion
from ..db.review_models import Calibration
from ..db.sec_models import AuditLog
from ..deps import AppState
from ..errors import ApiError, not_found
from ..stores.jobs import PgJobQueue
from .attack_lib import taxonomy
from .audit import audit, verify_chain
from .jobs import JobContext, handler
from .posture import PostureOut, build_posture
from .reports import run_report
from .runs import platform_version

__all__ = [
    "EvidenceIn",
    "EvidencePackOut",
    "create_pack",
    "download_pack",
    "get_pack",
    "list_packs",
]

log = logging.getLogger("gauntlet.evidence")

Framework = Literal["owasp-llm", "owasp-agentic", "nist-ai-rmf"]
MAX_RUNS = 20
AUDIT_ROWS = 200
DECISION_DAYS = 30
STRIP_KEYS = {"payload", "attack_payload", "prompt_injection_text"}  # attack text: ids only
WORDING = (
    "This pack is evidence supporting a release decision. It does not certify compliance with "
    "any standard or law, and it covers only what was tested."
)
# own wording; the NIST AI RMF function names are the only NIST terms used
NIST_MAP = {
    "GOVERN": [
        "policy versions and gateway decision summaries",
        "audit log excerpt with chain check",
    ],
    "MAP": ["tool inventory and blast radius in the posture report"],
    "MEASURE": ["run reports with intervals", "calibration results", "coverage matrix"],
    "MANAGE": ["open findings and recommendations in the posture report"],
}


class EvidenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_version_id: str
    frameworks: list[Framework] = Field(default_factory=lambda: ["owasp-llm"])


class EvidencePackOut(BaseModel):
    id: str
    agent_version_id: str
    frameworks: list[str]
    status: str
    sha256: str | None
    signed: bool
    error: str | None
    created_at: datetime
    finished_at: datetime | None


def _out(r: EvidencePack) -> EvidencePackOut:
    return EvidencePackOut.model_validate(r, from_attributes=True)


async def create_pack(
    state: AppState, s: AsyncSession, ws: str, body: EvidenceIn, actor: str
) -> EvidencePackOut:
    if state.object_store is None:
        raise ApiError(503, "object_store_unavailable", "no object store is configured")
    av = await s.get(m.AgentVersion, body.agent_version_id)
    if av is None or av.workspace_id != ws:
        raise not_found("agent version", body.agent_version_id)
    row = EvidencePack(
        id=new_id("evp"), workspace_id=ws, agent_version_id=av.id,
        frameworks=sorted(set(body.frameworks)), status="queued",
    )  # fmt: skip
    s.add(row)
    await s.flush()
    await audit(s, ws, actor, "evidence_pack.create", "evidence_pack", row.id,
                {"agent_version_id": av.id, "frameworks": row.frameworks})  # fmt: skip
    await PgJobQueue(state.sm).enqueue(ws, "evidence_pack", {"pack_id": row.id}, session=s)
    await s.commit()
    await s.refresh(row)
    return _out(row)


async def list_packs(s: AsyncSession, ws: str) -> list[EvidencePackOut]:
    rows = (
        await s.execute(
            select(EvidencePack)
            .where(EvidencePack.workspace_id == ws)
            .order_by(EvidencePack.created_at.desc())
            .limit(100)
        )
    ).scalars()
    return [_out(r) for r in rows]


async def _owned(s: AsyncSession, ws: str, pack_id: str) -> EvidencePack:
    row = await s.get(EvidencePack, pack_id)
    if row is None or row.workspace_id != ws:
        raise not_found("evidence pack", pack_id)
    return row


async def get_pack(s: AsyncSession, ws: str, pack_id: str) -> EvidencePackOut:
    return _out(await _owned(s, ws, pack_id))


async def download_pack(
    state: AppState, s: AsyncSession, ws: str, pack_id: str, actor: str
) -> bytes:
    row = await _owned(s, ws, pack_id)
    if row.status != "done" or not row.object_key:
        raise ApiError(409, "pack_not_ready", f"the pack is {row.status}")
    if state.object_store is None:
        raise ApiError(503, "object_store_unavailable", "no object store is configured")
    await audit(s, ws, actor, "evidence_pack.download", "evidence_pack", pack_id, {})
    await s.commit()
    return await state.object_store.get(row.object_key)


# --------------------------------------------------------------------------- building


def _jdump(doc: Any) -> bytes:
    return (json.dumps(doc, sort_keys=True, indent=2, default=str) + "\n").encode()


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k not in STRIP_KEYS}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [x for k, v in value.items() for x in [str(k), *_strings(v)]]
    if isinstance(value, list):
        return [x for v in value for x in _strings(v)]
    return []


def _scan(path: str, data: bytes, *, personal: bool) -> int:
    """Hits in the text of a file. JSON is scanned string by string: digits of separate numbers
    must not be read as one phone or card number."""
    if path.endswith(".json"):
        chunks = _strings(json.loads(data))
    else:
        chunks = [data.decode("utf-8", "replace")]
    hits = 0
    for t in chunks:
        hits += len(detect_secret(t))
        if personal:
            hits += len(detect_pii(t))
    return hits


class PackFailed(Exception):
    pass


async def _agentic_coverage(posture: PostureOut) -> list[dict[str, Any]]:
    tx = taxonomy()
    attempts: dict[str, int] = {}
    for c in posture.coverage:
        attempts[c.category] = attempts.get(c.category, 0) + c.attempts
    ids: dict[str, list[str]] = {}
    for cat in tx.categories:
        for oid in cat.owasp_agentic:
            ids.setdefault(oid, []).append(cat.id)
    return [
        {"framework": "owasp_agentic", "id": oid, "categories": sorted(cats),
         "attempts": sum(attempts.get(c, 0) for c in cats)}
        for oid, cats in sorted(ids.items())
    ]  # fmt: skip


async def _gather(
    state: AppState, s: AsyncSession, row: EvidencePack, av: m.AgentVersion
) -> dict[str, bytes]:
    ws = row.workspace_id
    files: dict[str, bytes] = {}
    runs = list(
        (
            await s.execute(
                select(m.Run)
                .where(
                    m.Run.workspace_id == ws,
                    m.Run.agent_version_id == av.id,
                    m.Run.status == "done",
                    m.Run.purpose != "import",
                )
                .order_by(m.Run.finished_at.desc())
                .limit(MAX_RUNS)
            )
        ).scalars()
    )
    for r in runs:
        files[f"runs/{r.id}/manifest.json"] = _jdump(r.manifest)
        files[f"runs/{r.id}/report.json"] = (
            (await run_report(s, r)).model_dump_json(indent=2).encode()
        )
    posture = PostureOut.model_validate(await build_posture(s, ws, av.agent_id, av.id, None))
    files["posture.json"] = posture.model_dump_json(indent=2).encode()
    from gauntlet_core.security.posture import render_markdown

    files["posture.md"] = render_markdown(posture).encode()
    for fw in row.frameworks:
        if fw == "owasp-llm":
            doc: Any = [c.model_dump() for c in posture.compliance]
        elif fw == "owasp-agentic":
            doc = await _agentic_coverage(posture)
        else:
            doc = {"framework": "nist_ai_rmf", "map": NIST_MAP}
        files[f"coverage/{fw}.json"] = _jdump(doc)
    cals = (
        await s.execute(
            select(Calibration)
            .where(Calibration.workspace_id == ws)
            .order_by(Calibration.created_at.desc())
            .limit(50)
        )
    ).scalars()
    files["calibrations.json"] = _jdump(
        [
            {"id": c.id, "rubric_id": c.rubric_id, "rubric_version": c.rubric_version,
             "status": c.status, "gating_allowed": c.gating_allowed, "threshold": c.threshold,
             "golden_count": c.golden_count, "stale": c.stale, "result": c.result}
            for c in cals
        ]
    )  # fmt: skip
    pols = (
        await s.execute(
            select(PolicyVersion)
            .where(PolicyVersion.workspace_id == ws)
            .order_by(PolicyVersion.id, PolicyVersion.version)
        )
    ).scalars()
    since = datetime.now(UTC) - timedelta(days=DECISION_DAYS)
    summary: dict[str, dict[str, int]] = {}
    for pid, action, n in (
        await s.execute(
            select(GatewayDecisionRow.policy_id, GatewayDecisionRow.action, func.count())
            .where(GatewayDecisionRow.workspace_id == ws, GatewayDecisionRow.ts >= since)
            .group_by(GatewayDecisionRow.policy_id, GatewayDecisionRow.action)
        )
    ).all():
        summary.setdefault(pid, {})[action] = int(n)
    files["policies.json"] = _jdump(
        {
            "policy_versions": [
                {"id": p.id, "version": p.version, "name": p.name, "status": p.status,
                 "mode": p.doc.get("mode"), "rules": [
                     {"id": r.get("id"), "action": r.get("action"), "severity": r.get("severity")}
                     for r in p.doc.get("rules", [])]}
                for p in pols
            ],
            "gateway_decisions_last_30d": summary,
        }
    )  # fmt: skip
    rows = list(
        (
            await s.execute(
                select(AuditLog)
                .where(AuditLog.workspace_id == ws)
                .order_by(AuditLog.seq.desc())
                .limit(AUDIT_ROWS)
            )
        ).scalars()
    )[::-1]
    full = await verify_chain(s, ws)
    files[AUDIT_EXCERPT] = _jdump(
        {
            "anchor_prev_hash": rows[0].prev_hash if rows else None,
            "rows": [
                {"id": r.id, "workspace_id": r.workspace_id, "ts": r.ts.astimezone(UTC).isoformat(),
                 "actor": r.actor, "action": r.action, "subject_type": r.subject_type,
                 "subject_id": r.subject_id, "detail": r.detail, "prev_hash": r.prev_hash,
                 "hash": r.hash, "seq": r.seq}
                for r in rows
            ],
        }
    )  # fmt: skip
    files["audit/verification.json"] = _jdump(
        {
            "full_chain": full.model_dump(),
            "excerpt_rows": len(rows),
            "generated_at": datetime.now(UTC),
        }
    )
    run_ids = [r.id for r in runs]
    cassettes = []
    if run_ids:
        for eid, key in (
            await s.execute(
                text(
                    "SELECT a.subject_id, a.detail ->> 'key' FROM audit_log a JOIN episodes e "
                    "ON e.id = a.subject_id WHERE a.workspace_id = :ws "
                    "AND a.action = 'cassette.archived' AND e.run_id = ANY(:runs) ORDER BY a.seq"
                ),
                {"ws": ws, "runs": run_ids},
            )
        ).all():
            cassettes.append({"episode_id": eid, "object_key": key})
    files["cassettes.json"] = _jdump({"archived": cassettes})
    files["README.txt"] = (
        f"{WORDING}\n\nVerify offline with `gauntlet evidence verify <pack.zip>`.\n"
    ).encode()
    return files


def _protect(files: dict[str, bytes], key: bytes, scope: str) -> tuple[dict[str, bytes], int]:
    """Redact every file but the audit excerpt, then scan all of them. Returns the files and
    the number of redactions; raises PackFailed on a residual hit (path only)."""
    red = Redactor(key=key, scope=scope)
    out: dict[str, bytes] = {}
    for path, data in files.items():
        if path.startswith("audit/"):
            out[path] = data
        elif path.endswith(".json"):
            out[path] = _jdump(red.redact_json(_strip(json.loads(data))))
        else:
            out[path] = red.redact_text(data.decode()).encode()
    for path, data in out.items():
        if _scan(path, data, personal=not path.startswith("audit/")):
            raise PackFailed(f"detector hit in {path}")
    return out, sum(red.counts.values())


async def _build(state: AppState, pack_id: str) -> dict[str, Any]:
    async with state.sm() as s:
        row = await s.get(EvidencePack, pack_id)
        if row is None:
            return {"status": "missing"}
        av = await s.get(m.AgentVersion, row.agent_version_id)
        assert av is not None
        files = await _gather(state, s, row, av)
        ws, frameworks = row.workspace_id, list(row.frameworks)
        label, agent_id = av.label, av.agent_id
    protected, redactions = _protect(files, state.settings.redaction_key(), f"evidence:{pack_id}")
    seed = state.settings.evidence_signing_key
    pub = None
    if seed:
        try:
            pub = public_key_b64(seed)
        except Exception as e:
            raise PackFailed("the evidence signing key is invalid") from e
    manifest = {
        "schema_version": 1, "pack_id": pack_id, "generated_at": datetime.now(UTC).isoformat(),
        "platform_version": platform_version(),
        "agent_version": {"id": av.id, "label": label, "agent_id": agent_id},
        "frameworks": frameworks, "wording": WORDING, "redactions": redactions,
        "signed": bool(seed), "public_key": pub,
        "signing_note": None if seed else "unsigned: no evidence signing key is configured",
        "files": sorted(protected),
    }  # fmt: skip
    protected["manifest.json"] = _jdump(manifest)
    blob = build_zip(protected, signing_seed_b64=seed or None)
    key = f"evidence/{ws}/{pack_id}.zip"
    assert state.object_store is not None
    await state.object_store.put(key, blob, "application/zip")
    async with state.sm() as s, s.begin():
        row = await s.get(EvidencePack, pack_id)
        assert row is not None
        row.status, row.object_key, row.signed = "done", key, bool(seed)
        row.sha256, row.finished_at, row.error = (
            hashlib.sha256(blob).hexdigest(),
            datetime.now(UTC),
            None,
        )
    return {"status": "done", "bytes": len(blob), "signed": bool(seed)}


@handler("evidence_pack")
async def evidence_pack(ctx: JobContext) -> dict[str, Any]:
    pack_id = str(ctx.payload["pack_id"])
    if ctx.state.object_store is None:
        raise ApiError(503, "object_store_unavailable", "no object store is configured")
    async with ctx.state.sm() as s, s.begin():
        row = await s.get(EvidencePack, pack_id)
        if row is not None:
            row.status = "running"
    try:
        return await _build(ctx.state, pack_id)
    except PackFailed as e:
        async with ctx.state.sm() as s, s.begin():
            row = await s.get(EvidencePack, pack_id)
            if row is not None:
                row.status, row.error, row.finished_at = "failed", str(e), datetime.now(UTC)
        return {"status": "failed", "error": str(e)}  # fail closed, job done (no retry storm)
