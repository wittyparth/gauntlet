"""Cassette export, archive and import over the seeded demo episodes."""

from __future__ import annotations

import json

import pytest
from gauntlet_core.objectstore import LocalFsObjectStore
from sqlalchemy import text

pytestmark = pytest.mark.integration

SECRET = "sk-planted-secret-value-9876"


async def seeded(client) -> dict:
    return (await client.post("/v1/dev/seed", json={"reset": False})).json()


async def test_export_content_type_and_manifest(client):
    seed = await seeded(client)
    r = await client.get(f"/v1/episodes/{seed['failed_episode_id']}/cassette")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(line) for line in r.text.splitlines()]
    head = lines[0]
    assert head["t"] == "header" and head["format"] == "gauntlet-cassette/1"
    man = head["manifest"]
    assert man["scenario"]["id"] == "scn_ecom_07" and man["world"]["tools"] and man["persona"]
    assert man["agent_version"]["target"]["model"] and man["rng_seed"] >= 0
    assert {ln["t"] for ln in lines[1:]} == {"event", "effect"}
    assert (await client.get("/v1/episodes/nope/cassette")).status_code == 404


async def test_a_planted_secret_never_appears_in_an_export(client, sm):
    seed = await seeded(client)
    ep = seed["failed_episode_id"]
    assert (
        await client.post("/v1/secrets", json={"name": "planted", "value": SECRET})
    ).status_code == 201
    async with sm() as s, s.begin():  # a leak that slipped past append-time redaction
        await s.execute(
            text(
                "UPDATE events SET doc = jsonb_set(doc, '{payload,leak}', CAST(:v AS jsonb)) "
                "WHERE episode_id = :e AND seq = 1"
            ),
            {"v": json.dumps(f"token {SECRET} here"), "e": ep},
        )
    r = await client.get(f"/v1/episodes/{ep}/cassette")
    assert r.status_code == 200 and SECRET not in r.text and "[REDACTED]" in r.text


async def test_import_round_trip_hidden_from_default_run_list(client):
    seed = await seeded(client)
    ep = seed["failed_episode_id"]
    text_ = (await client.get(f"/v1/episodes/{ep}/cassette")).text
    r = await client.post(
        "/v1/cassettes", content=text_, headers={"Content-Type": "application/x-ndjson"}
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["scenario_id"] == "scn_ecom_07" and out["scenario_version"] == 1
    detail = (await client.get(f"/v1/episodes/{out['episode_id']}")).json()
    assert detail["status"] == "done" and detail["outcome"] == "failed" and not detail["partial"]
    original = (await client.get(f"/v1/episodes/{ep}")).json()
    assert [e["payload"] for e in detail["events"]] == [e["payload"] for e in original["events"]]
    assert detail["diff"]["changes"] and detail["verdicts"]
    run = (await client.get(f"/v1/runs/{out['run_id']}")).json()
    assert run["purpose"] == "import" and run["status"] == "done"
    default = [r["id"] for r in (await client.get("/v1/runs")).json()["items"]]
    assert out["run_id"] not in default
    shown = (await client.get("/v1/runs", params={"purpose": "import"})).json()["items"]
    assert [r["id"] for r in shown] == [out["run_id"]]
    assert out["run_id"] in [
        r["id"]
        for r in (await client.get("/v1/runs", params={"include_imports": True})).json()["items"]
    ]
    # an imported cassette strict-replays identically too
    again = await client.post(f"/v1/episodes/{out['episode_id']}/replay", json={"mode": "strict"})
    assert again.json()["identical"] is True


async def test_import_bumps_the_scenario_version_when_it_differs(client, sm):
    seed = await seeded(client)
    ep = seed["failed_episode_id"]
    lines = (await client.get(f"/v1/episodes/{ep}/cassette")).text.splitlines()
    head = json.loads(lines[0])
    head["manifest"]["scenario"]["title"] = "Changed title"
    lines[0] = json.dumps(head)
    r = await client.post("/v1/cassettes", content="\n".join(lines) + "\n")
    assert r.status_code == 201 and r.json()["scenario_version"] == 2
    got = (await client.get("/v1/scenarios/scn_ecom_07")).json()
    assert got["version"] == 2 and got["scenario"]["title"] == "Changed title"


async def test_import_rejects_oversize_and_malformed_lines(client):
    seed = await seeded(client)
    text_ = (await client.get(f"/v1/episodes/{seed['failed_episode_id']}/cassette")).text
    big = await client.post("/v1/cassettes", content=text_ + "x" * (21 * 1024 * 1024))
    assert big.status_code == 413 and big.json()["error"]["code"] == "cassette_too_large"
    lines = text_.splitlines()
    lines[3] = "{not json"
    bad = await client.post("/v1/cassettes", content="\n".join(lines))
    assert bad.status_code == 422
    err = bad.json()["error"]
    assert err["code"] == "invalid_cassette" and err["detail"] == {"line": 4}
    gap = text_.splitlines()
    del gap[2]
    assert (await client.post("/v1/cassettes", content="\n".join(gap))).status_code == 422


async def test_archive_to_compose_s3_returns_a_presigned_url(client, state):
    import os

    from gauntlet_core.objectstore import S3ObjectStore

    seed = await seeded(client)
    ep = seed["failed_episode_id"]
    state.object_store = S3ObjectStore(
        os.environ.get("TEST_S3_BUCKET", "gauntlet"),
        endpoint_url=os.environ.get("TEST_S3_ENDPOINT", "http://localhost:9000"),
        access_key=os.environ.get("S3_ACCESS_KEY", "minio-dev"),
        secret_key=os.environ.get("S3_SECRET_KEY", "minio-dev-secret"),
    )
    out = (await client.post(f"/v1/episodes/{ep}/cassette/archive")).json()
    assert out["url"].startswith("http") and "X-Amz-Signature" in out["url"]
    stored = (await state.object_store.get(out["key"])).decode()
    assert json.loads(stored.splitlines()[0])["manifest"]["episode_id"] == ep


async def test_archive_stores_the_export_and_returns_a_url(client, state, tmp_path):
    seed = await seeded(client)
    ep = seed["failed_episode_id"]
    assert (await client.post(f"/v1/episodes/{ep}/cassette/archive")).status_code == 503
    state.object_store = LocalFsObjectStore(tmp_path)
    r = await client.post(f"/v1/episodes/{ep}/cassette/archive")
    assert r.status_code == 200, r.text
    out = r.json()
    ws_key = out["key"]
    assert ws_key.startswith("cassettes/ws_test/") and ws_key.endswith(f"{ep}.jsonl")
    assert out["url"].startswith("file://")
    stored = (tmp_path / ws_key).read_text()
    assert json.loads(stored.splitlines()[0])["manifest"]["episode_id"] == ep
