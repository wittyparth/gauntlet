from __future__ import annotations

import dataclasses

import pytest
from google.protobuf.json_format import ParseDict
from ingest_helpers import fixture, post, session_doc
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def convs(client, **params):
    return (await client.get("/v1/production/conversations", params=params)).json()["items"]


async def test_json_export_creates_a_conversation(client):
    r = await post(client, fixture("openinference_support"))
    assert r.status_code == 200 and r.json() == {"partialSuccess": {"rejectedSpans": 0}}
    (c,) = await convs(client)
    assert c["external_session_id"] == "sess-1" and c["event_count"] == 7
    assert c["signals"]["turns"] == 2 and c["signals"]["tool_calls"] == 1


async def test_protobuf_export(client):
    req = ParseDict(fixture("genai_support"), ExportTraceServiceRequest())
    r = await client.post(
        "/v1/traces",
        content=req.SerializeToString(),
        headers={"content-type": "application/x-protobuf"},
    )
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-protobuf")
    (c,) = await convs(client)
    assert c["external_session_id"] == "sess-2" and c["event_count"] == 4


async def test_scope_is_required(client, sm):
    from gauntlet_server.auth import hash_key

    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO api_keys (id, workspace_id, hash, prefix, name, scopes) VALUES "
                "('key_ro', 'ws_test', :h, 'gk_ro', 'ro', '[\"read\"]'), "
                "('key_in', 'ws_test', :i, 'gk_in', 'in', '[\"ingest\"]')"
            ),
            {"h": hash_key("gk_readonly"), "i": hash_key("gk_ingest")},
        )
    doc = fixture("genai_support")
    ro = await client.post("/v1/traces", json=doc, headers={"Authorization": "Bearer gk_readonly"})
    assert ro.status_code == 403
    ok = await client.post("/v1/traces", json=doc, headers={"Authorization": "Bearer gk_ingest"})
    assert ok.status_code == 200
    anon = await client.post("/v1/traces", json=doc, headers={"Authorization": "Bearer nope"})
    assert anon.status_code == 401


async def test_duplicate_spans_are_idempotent(client):
    doc = fixture("openinference_support")
    await post(client, doc)
    again = await post(client, doc)
    assert again.status_code == 200
    (c,) = await convs(client)
    assert c["event_count"] == 7
    stats = (await client.get("/v1/production/stats")).json()
    assert stats["spans"] == 6 and stats["conversations"] == 1


async def test_late_spans_extend_the_conversation_in_time_order(client):
    full = fixture("openinference_support")
    spans = full["resourceSpans"][0]["scopeSpans"][0]["spans"]

    def part(sp):
        return {"resourceSpans": [{"scopeSpans": [{"spans": sp}]}]}

    await post(client, part(spans[:3]))
    await post(client, part(spans[3:]))
    (c,) = await convs(client)
    detail = (await client.get(f"/v1/production/conversations/{c['id']}")).json()
    kinds = [e["kind"] for e in detail["events"]]
    assert [e["seq"] for e in detail["events"]] == list(range(1, len(kinds) + 1))
    assert kinds[0] == "user_message" and kinds[-1] == "agent_message"
    times = [e["sim_time"] for e in detail["events"]]
    assert times == sorted(times)


async def test_oversize_payloads_get_413_and_are_counted(client, state):
    state.settings = dataclasses.replace(state.settings, ingest_max_bytes=200)
    r = await post(client, fixture("openinference_support"))
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"
    state.settings = dataclasses.replace(state.settings, ingest_max_bytes=10**6, ingest_max_spans=2)
    assert (await post(client, fixture("openinference_support"))).status_code == 413
    stats = (await client.get("/v1/production/stats")).json()
    assert stats["rejected"] == 1 + 6 and stats["spans"] == 0


async def test_invalid_bodies_are_400(client):
    js = {"content-type": "application/json"}
    pb = {"content-type": "application/x-protobuf"}
    assert (await client.post("/v1/traces", content=b"{nope", headers=js)).status_code == 400
    assert (await client.post("/v1/traces", content=b"\xff\xff", headers=pb)).status_code == 400
    assert (await client.post("/v1/traces", json=[1, 2])).status_code == 400


async def test_sampling_drops_whole_sessions_deterministically(client, state):
    state.settings = dataclasses.replace(state.settings, ingest_sample_rate=0.5)
    sessions = [f"s{i:02d}" for i in range(24)]
    for sid in sessions:
        await post(client, session_doc(sid, n_turns=2))
    kept = {c["external_session_id"] for c in await convs(client, limit=100)}
    assert 4 <= len(kept) <= 20
    assert all(
        c["event_count"] == 4 for c in await convs(client, limit=100)
    )  # never half a session
    for sid in sessions:  # a second pass keeps and drops exactly the same sessions
        await post(client, session_doc(sid, n_turns=2, trace="f" * 32))
    assert {c["external_session_id"] for c in await convs(client, limit=100)} == kept
    state.settings = dataclasses.replace(state.settings, ingest_sample_rate=0.0)
    await post(client, session_doc("zzz", 1))
    assert "zzz" not in {c["external_session_id"] for c in await convs(client, limit=100)}


async def test_rate_limit(client, state):
    async for k in state.redis.scan_iter("gauntlet:ingest:rl:*"):
        await state.redis.delete(k)
    state.settings = dataclasses.replace(state.settings, ingest_rate_per_s=2)
    codes = [(await post(client, session_doc(f"r{i}", 1))).status_code for i in range(6)]
    assert 429 in codes and codes[0] == 200


async def test_unknown_agent_is_404(client):
    assert (await post(client, fixture("genai_support"), agent_id="agt_nope")).status_code == 404
