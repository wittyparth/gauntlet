"""`gauntlet evidence create` (mocked server) and `verify` (offline)."""

from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime

import httpx
import respx
from cli_helpers import invoke
from gauntlet_cli.commands import evidence
from gauntlet_core.audit_chain import GENESIS, row_hash
from gauntlet_core.evidence import build_zip, public_key_b64

API = "http://host.test"
SEED = base64.b64encode(os.urandom(32)).decode()


def excerpt() -> dict:
    rows, prev = [], GENESIS
    for i in range(3):
        ts = datetime(2026, 1, 1, i, tzinfo=UTC)
        h = row_hash(prev, id=f"aud_{i}", workspace_id="ws", ts=ts, actor="a", action="x",
                     subject_type="t", subject_id="s", detail={"n": i})  # fmt: skip
        rows.append({"id": f"aud_{i}", "workspace_id": "ws", "ts": ts.isoformat(), "actor": "a",
                     "action": "x", "subject_type": "t", "subject_id": "s", "detail": {"n": i},
                     "prev_hash": prev, "hash": h})  # fmt: skip
        prev = h
    return {"anchor_prev_hash": GENESIS, "rows": rows}


def make_pack(tmp_path, *, signed=True, tamper=False):
    ex = excerpt()
    if tamper:
        ex["rows"][1]["actor"] = "mallory"
    manifest = {"public_key": public_key_b64(SEED) if signed else None}
    blob = build_zip(
        {"manifest.json": json.dumps(manifest).encode(),
         "audit/excerpt.json": json.dumps(ex).encode(), "posture.json": b"{}"},
        signing_seed_b64=SEED if signed else None,
    )  # fmt: skip
    p = tmp_path / "pack.zip"
    p.write_bytes(blob)
    return p


def test_verify_signed_pack_offline(runner, tmp_path):
    p = make_pack(tmp_path)
    res = invoke(runner, ["evidence", "verify", str(p)])
    assert res.exit_code == 0, res.stdout + res.stderr
    assert "checksums:   ok" in res.stdout and "audit chain: valid" in res.stdout
    assert "signature:   valid" in res.stdout
    keyed = invoke(runner, ["evidence", "verify", str(p), "--public-key", public_key_b64(SEED)])
    assert keyed.exit_code == 0
    wrong = invoke(runner, ["evidence", "verify", str(p), "--public-key",
                            public_key_b64(base64.b64encode(os.urandom(32)).decode())])  # fmt: skip
    assert wrong.exit_code == 1 and "signature:   invalid" in wrong.stdout


def test_verify_detects_a_tampered_audit_row_and_a_bad_file(runner, tmp_path):
    res = invoke(runner, ["evidence", "verify", str(make_pack(tmp_path, tamper=True)), "--json"])
    out = json.loads(res.stdout)
    assert res.exit_code == 1 and out["audit_chain"] == "invalid" and not out["ok"]
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"not a zip")
    assert invoke(runner, ["evidence", "verify", str(junk)]).exit_code == 1
    assert invoke(runner, ["evidence", "verify", str(tmp_path / "missing.zip")]).exit_code == 2


def test_unsigned_pack_verifies_and_reports_absent_signature(runner, tmp_path):
    res = invoke(runner, ["evidence", "verify", str(make_pack(tmp_path, signed=False))])
    assert res.exit_code == 0 and "signature:   absent" in res.stdout


@respx.mock
def test_create_polls_then_downloads(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "_sleep", lambda _s: None)
    pack = {"id": "evp_1", "status": "queued", "signed": True, "sha256": "ab" * 32, "error": None}
    respx.post(f"{API}/v1/evidence-packs").mock(return_value=httpx.Response(202, json=pack))
    respx.get(f"{API}/v1/evidence-packs/evp_1").mock(
        side_effect=[httpx.Response(200, json={**pack, "status": "running"}),
                     httpx.Response(200, json={**pack, "status": "done"})]
    )  # fmt: skip
    blob = make_pack(tmp_path).read_bytes()
    respx.get(f"{API}/v1/evidence-packs/evp_1/download").mock(
        return_value=httpx.Response(200, content=blob)
    )
    out = tmp_path / "got.zip"
    args = ["evidence", "create", "--agent-version", "agv_1", "--framework", "owasp-llm"]
    res = invoke(runner, [*args, "-o", str(out), "--api-url", API, "--api-key", "gk"])
    assert res.exit_code == 0, res.stderr
    assert out.read_bytes() == blob and "wrote" in res.stdout


@respx.mock
def test_create_failed_pack_exits_3(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "_sleep", lambda _s: None)
    pack = {"id": "evp_1", "status": "failed", "signed": False, "sha256": None,
            "error": "detector hit in posture.json"}  # fmt: skip
    respx.post(f"{API}/v1/evidence-packs").mock(return_value=httpx.Response(202, json=pack))
    args = ["evidence", "create", "--agent-version", "agv_1", "-o", str(tmp_path / "x.zip")]
    res = invoke(runner, [*args, "--api-url", API, "--api-key", "gk"])
    assert res.exit_code == 3 and "detector hit" in res.stderr
