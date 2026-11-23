"""Evidence packs: contents, checksums, audit chain (and tamper), planted secret, signature,
unsigned flag, detector failure, offline verification."""

from __future__ import annotations

import base64
import dataclasses
import io
import json
import os
import zipfile

import pytest
from gauntlet_core.evidence import build_zip, public_key_b64, verify_pack
from gauntlet_core.objectstore import LocalFsObjectStore
from gauntlet_server.services import evidence
from gauntlet_server.services.jobs import run_job
from gauntlet_server.stores.jobs import PgJobQueue
from sqlalchemy import text

pytestmark = pytest.mark.integration

PLANTED = "sk-PLANTEDSECRETVALUE0123456789abcdef"
SEED = base64.b64encode(os.urandom(32)).decode()


@pytest.fixture
def store(state, tmp_path):
    state.object_store = LocalFsObjectStore(tmp_path / "objects")
    return state.object_store


async def run_pack_jobs(state) -> None:
    queue = PgJobQueue(state.sm)
    for lease in await queue.claim("t", 10, 60):
        if lease.kind == "evidence_pack":
            await run_job(state, queue, lease)


async def make_pack(client, state, *, signed: bool = True, frameworks=None) -> dict:
    state.settings = dataclasses.replace(
        state.settings, evidence_signing_key=SEED if signed else ""
    )
    body = {"agent_version_id": "agv_demo"}
    if frameworks:
        body["frameworks"] = frameworks
    r = await client.post("/v1/evidence-packs", json=body)
    assert r.status_code == 202, r.text
    await run_pack_jobs(state)
    return (await client.get(f"/v1/evidence-packs/{r.json()['id']}")).json()


async def plant(client, sm) -> None:
    await client.post("/v1/dev/seed", json={"reset": False})
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "UPDATE runs SET manifest = jsonb_set(manifest, '{agent_version,label}', "
                "to_jsonb(CAST(:v AS text)))"
            ),
            {"v": f"prod build {PLANTED}"},
        )


def open_zip(data: bytes) -> dict[str, bytes]:
    z = zipfile.ZipFile(io.BytesIO(data))
    return {n: z.read(n) for n in z.namelist()}


async def test_pack_contents_checksums_signature_and_no_planted_secret(client, state, sm, store):
    await plant(client, sm)
    pack = await make_pack(client, state, frameworks=["owasp-llm", "owasp-agentic", "nist-ai-rmf"])
    assert pack["status"] == "done", pack["error"]
    assert pack["signed"] and pack["sha256"]
    dl = await client.get(f"/v1/evidence-packs/{pack['id']}/download")
    assert dl.status_code == 200 and dl.headers["content-type"] == "application/zip"
    files = open_zip(dl.content)
    names = set(files)
    assert {
        "manifest.json", "SHA256SUMS", "SIGNATURE", "posture.json", "posture.md",
        "calibrations.json", "policies.json", "cassettes.json", "README.txt",
        "audit/excerpt.json", "audit/verification.json",
        "coverage/owasp-llm.json", "coverage/owasp-agentic.json", "coverage/nist-ai-rmf.json",
    } <= names  # fmt: skip
    assert any(n.startswith("runs/") and n.endswith("/manifest.json") for n in names)
    assert any(n.startswith("runs/") and n.endswith("/report.json") for n in names)
    manifest = json.loads(files["manifest.json"])
    assert manifest["signed"] and manifest["public_key"] == public_key_b64(SEED)
    assert "evidence supporting" in manifest["wording"] and "compliant" not in manifest["wording"]
    assert manifest["redactions"] >= 1
    owasp = json.loads(files["coverage/owasp-llm.json"])
    assert {r["id"] for r in owasp} >= {"LLM01", "LLM10"}
    # planted secret: absent from every file, in every encoding the zip holds
    for name, data in files.items():
        assert PLANTED.encode() not in data, name
        assert PLANTED.split("-", 1)[1].encode() not in data, name
    rep = verify_pack(dl.content)
    assert rep.ok and rep.checksums and rep.audit_chain == "valid" and rep.signature == "valid"
    assert verify_pack(dl.content, public_key_b64_=public_key_b64(SEED)).signature == "valid"
    other = public_key_b64(base64.b64encode(os.urandom(32)).decode())
    bad = verify_pack(dl.content, public_key_b64_=other)
    assert bad.signature == "invalid" and not bad.ok


async def test_audit_chain_verification_fails_on_a_tampered_row(client, state, sm, store):
    await plant(client, sm)
    pack = await make_pack(client, state)
    files = open_zip((await client.get(f"/v1/evidence-packs/{pack['id']}/download")).content)
    excerpt = json.loads(files["audit/excerpt.json"])
    assert len(excerpt["rows"]) >= 1
    excerpt["rows"][-1]["actor"] = "someone-else"
    files["audit/excerpt.json"] = json.dumps(excerpt).encode()
    for k in ("SHA256SUMS", "SIGNATURE"):
        files.pop(k)
    rebuilt = build_zip(files)  # checksums consistent, chain not
    rep = verify_pack(rebuilt)
    assert rep.audit_chain == "invalid" and not rep.ok and rep.checksums
    # editing a file in place without rebuilding the sums breaks the checksum instead
    raw = open_zip((await client.get(f"/v1/evidence-packs/{pack['id']}/download")).content)
    raw["posture.json"] = raw["posture.json"] + b" "
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, d in raw.items():
            z.writestr(n, d)
    rep2 = verify_pack(buf.getvalue())
    assert not rep2.ok and not rep2.checksums and any("posture.json" in p for p in rep2.problems)


async def test_unsigned_pack_is_flagged(client, state, sm, store):
    await plant(client, sm)
    pack = await make_pack(client, state, signed=False)
    assert pack["status"] == "done" and pack["signed"] is False
    files = open_zip((await client.get(f"/v1/evidence-packs/{pack['id']}/download")).content)
    assert "SIGNATURE" not in files
    manifest = json.loads(files["manifest.json"])
    assert manifest["signed"] is False and "unsigned" in manifest["signing_note"]
    assert verify_pack(open_zip_bytes(files)).signature == "absent"


def open_zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, d in files.items():
            z.writestr(n, d)
    return buf.getvalue()


async def test_detector_hit_fails_the_pack_without_quoting_the_match(
    client, state, sm, store, monkeypatch
):
    await plant(client, sm)
    monkeypatch.setattr(evidence, "detect_pii", lambda _t: [object()])
    pack = await make_pack(client, state)
    assert pack["status"] == "failed" and "detector hit in" in pack["error"]
    assert PLANTED not in json.dumps(pack)
    assert (await client.get(f"/v1/evidence-packs/{pack['id']}/download")).status_code == 409


async def test_routes_errors_and_audit(client, state, sm, store):
    await plant(client, sm)
    assert (await client.get("/v1/evidence-packs/evp_nope")).status_code == 404
    bad = await client.post("/v1/evidence-packs", json={"agent_version_id": "agv_nope"})
    assert bad.status_code == 404
    odd = await client.post(
        "/v1/evidence-packs", json={"agent_version_id": "agv_demo", "frameworks": ["iso-27001"]}
    )
    assert odd.status_code == 422
    pack = await make_pack(client, state)
    assert (await client.get("/v1/evidence-packs")).json()[0]["id"] == pack["id"]
    await client.get(f"/v1/evidence-packs/{pack['id']}/download")
    async with sm() as s:
        acts = (
            (
                await s.execute(
                    text("SELECT action FROM audit_log WHERE subject_id = :i"), {"i": pack["id"]}
                )
            )
            .scalars()
            .all()
        )
    assert set(acts) == {"evidence_pack.create", "evidence_pack.download"}


async def test_no_object_store_is_503(client, state, sm):
    await plant(client, sm)
    state.object_store = None
    r = await client.post("/v1/evidence-packs", json={"agent_version_id": "agv_demo"})
    assert r.status_code == 503
