"""Alerts: de-duplication, silence, resolve, signed webhook, secrets stay out of rows and logs,
no channel means no network."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from gauntlet_server.services import alerts
from gauntlet_server.services.jobs import run_job
from gauntlet_server.stores.jobs import PgJobQueue
from sqlalchemy import text

pytestmark = pytest.mark.integration

HOOK_URL = "https://hooks.example.test/in/abc123-private-token"
SIGNING_KEY = "whsec_planted_signing_key_91"
WS = "ws_test"


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    async def fake(_host: str) -> list[str]:
        return ["93.184.216.34"]

    async def instant(_s: float) -> None:
        return None

    monkeypatch.setattr(alerts, "resolve", fake)
    monkeypatch.setattr(alerts, "sleep", instant)


async def breached_slo(client, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    agent = (await client.get(f"/v1/agents/{seed['agent_id']}")).json()["id"]
    slo = (
        await client.post(
            "/v1/slos",
            json={"agent_id": agent, "metric": "pass_rate", "objective": 0.9, "window_days": 7},
        )
    ).json()
    await set_outcomes(sm, seed["run_id"], 3)
    return seed, slo


async def set_outcomes(sm, run_id: str, passed: int) -> None:
    async with sm() as s, s.begin():
        await s.execute(
            text("UPDATE episodes SET outcome = 'failed', finished_at = now() WHERE run_id = :r"),
            {"r": run_id},
        )
        await s.execute(
            text(
                "UPDATE episodes SET outcome = 'passed' WHERE id IN "
                "(SELECT id FROM episodes WHERE run_id = :r ORDER BY id LIMIT :n)"
            ),
            {"r": run_id, "n": passed},
        )


async def webhook_channel(client, state, name="hook"):
    await state.secrets.put(WS, name, json.dumps({"url": HOOK_URL, "signing_key": SIGNING_KEY}))
    r = await client.post("/v1/alert-channels", json={"kind": "webhook", "secret_name": name})
    assert r.status_code == 201, r.text
    return r.json()


async def breach_rule(client, slo, channels):
    r = await client.post(
        "/v1/alert-rules",
        json={"kind": "breach", "slo_id": slo["id"], "channel_ids": [c["id"] for c in channels]},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def run_jobs(state) -> int:
    queue = PgJobQueue(state.sm)
    leases = [ls for ls in await queue.claim("t", 10, 30) if ls.kind == "alert_deliver"]
    for ls in leases:
        await run_job(state, queue, ls)
    return len(leases)


async def jobs_count(sm) -> int:
    async with sm() as s:
        return (
            await s.execute(text("SELECT count(*) FROM jobs WHERE kind = 'alert_deliver'"))
        ).scalar_one()


async def test_channel_validation_and_no_secret_in_response(client, state):
    r = await client.post("/v1/alert-channels", json={"kind": "webhook", "secret_name": "absent"})
    assert r.status_code == 422
    await state.secrets.put(WS, "bad", "not json")
    assert (
        await client.post("/v1/alert-channels", json={"kind": "webhook", "secret_name": "bad"})
    ).status_code == 422
    ch = await webhook_channel(client, state)
    listing = (await client.get("/v1/alert-channels")).text
    for body in (json.dumps(ch), listing):
        assert HOOK_URL not in body and SIGNING_KEY not in body and "abc123" not in body
    assert ch["secret_name"] == "hook"


async def test_breach_fires_one_deduplicated_signed_alert_then_resolves(client, state, sm):
    _, slo = await breached_slo(client, sm)
    ch = await webhook_channel(client, state)
    await breach_rule(client, slo, [ch])
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(HOOK_URL).respond(200)
        for _ in range(3):  # repeated ticks while firing: still one notification
            await alerts.evaluate_all(state)
            await run_jobs(state)
        assert route.call_count == 1
        req = route.calls[0].request
        ts, sig = req.headers["x-gauntlet-timestamp"], req.headers["x-gauntlet-signature"]
        assert sig == alerts.sign(SIGNING_KEY, ts, req.content)
        body = json.loads(req.content)
        assert body["event"] == "firing" and body["kind"] == "breach"
        assert body["payload"]["slo_id"] == slo["id"]
        firing = (await client.get("/v1/alerts?state=firing")).json()
        assert len(firing) == 1 and firing[0]["notified_at"]

        # recovery: the SLO is healthy again -> one resolve notification
        seed_run = (await client.get("/v1/runs")).json()["items"][0]["id"]
        await set_outcomes(sm, seed_run, 10)
        for _ in range(2):
            await alerts.evaluate_all(state)
            await run_jobs(state)
        assert route.call_count == 2
        assert json.loads(route.calls[1].request.content)["event"] == "resolved"
    assert (await client.get("/v1/alerts?state=firing")).json() == []
    assert len((await client.get("/v1/alerts?state=resolved")).json()) == 1


async def test_silence_window_suppresses_notification(client, state, sm):
    _, slo = await breached_slo(client, sm)
    ch = await webhook_channel(client, state)
    rule = await breach_rule(client, slo, [ch])
    until = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    # fire once with no channel notified yet: silence the rule first via a PATCH
    p = await client.patch(f"/v1/alert-rules/{rule['id']}", json={"silence_until": until})
    assert p.status_code == 200
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(HOOK_URL).respond(200)
        await alerts.evaluate_all(state)
        assert await jobs_count(sm) == 0 and route.call_count == 0
        alert = (await client.get("/v1/alerts?state=firing")).json()[0]
        assert alert["silenced_until"] is not None
        # an alert-level silence call works too and is audited
        r = await client.post(f"/v1/alerts/{alert['id']}/silence", json={"until": until})
        assert r.status_code == 200
        # silence ends: the still-firing alert is announced once
        await client.patch(f"/v1/alert-rules/{rule['id']}", json={"silence_until": None})
        await alerts.evaluate_all(state)
        await run_jobs(state)
        assert route.call_count == 1
    async with sm() as s:
        acts = (await s.execute(text("SELECT action FROM audit_log"))).scalars().all()
    assert "alert.silence" in acts and "alert_rule.update" in acts


async def test_no_channel_means_no_network_call(client, state, sm):
    _, slo = await breached_slo(client, sm)
    await breach_rule(client, slo, [])
    with respx.mock(assert_all_called=False) as mock:
        await alerts.evaluate_all(state)
        await run_jobs(state)
        assert len(mock.calls) == 0
    assert await jobs_count(sm) == 0
    assert len((await client.get("/v1/alerts?state=firing")).json()) == 1  # still recorded


async def test_secret_never_in_rows_or_logs(client, state, sm, caplog):
    _, slo = await breached_slo(client, sm)
    ch = await webhook_channel(client, state)
    await breach_rule(client, slo, [ch])
    caplog.set_level(logging.DEBUG)
    with respx.mock(assert_all_called=False) as mock:
        mock.post(HOOK_URL).mock(side_effect=httpx.ConnectError("boom " + HOOK_URL))
        await alerts.evaluate_all(state)
        await run_jobs(state)  # delivery fails, the job records a sanitised error
    async with sm() as s:
        dump = ""
        for table in ("alert_channels", "alert_rules", "alerts", "jobs", "audit_log"):
            rows = (await s.execute(text(f"SELECT t::text FROM {table} t"))).scalars().all()
            dump += "\n".join(rows)
    blob = dump + caplog.text
    assert HOOK_URL not in blob and SIGNING_KEY not in blob and "abc123" not in blob
    assert "ConnectError" in blob  # the class name is kept for diagnosis


async def test_retry_with_backoff_then_success(client, state, sm):
    _, slo = await breached_slo(client, sm)
    ch = await webhook_channel(client, state)
    await breach_rule(client, slo, [ch])
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(HOOK_URL).mock(
            side_effect=[httpx.Response(503), httpx.Response(502), httpx.Response(200)]
        )
        await alerts.evaluate_all(state)
        assert await run_jobs(state) == 1
        assert route.call_count == 3
    assert (await client.get("/v1/alerts?state=firing")).json()[0]["notified_at"]


async def test_slack_and_email_channels(client, state, sm, monkeypatch):
    _, slo = await breached_slo(client, sm)
    await state.secrets.put(WS, "slack", "https://hooks.slack.example/T000/B000/xyz")
    await state.secrets.put(
        WS,
        "mail",
        json.dumps(
            {"host": "smtp.example.test", "from": "a@x.test", "to": ["b@x.test"], "starttls": False}
        ),
    )
    chans = [
        (await client.post("/v1/alert-channels", json={"kind": k, "secret_name": n})).json()
        for k, n in (("slack", "slack"), ("email", "mail"))
    ]
    await breach_rule(client, slo, chans)
    sent: list[str] = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent.append(host)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def send_message(self, msg):
            sent.append(msg["Subject"])

    monkeypatch.setattr(alerts, "SMTP_FACTORY", FakeSMTP)
    with respx.mock(assert_all_called=False) as mock:
        slack = mock.post("https://hooks.slack.example/T000/B000/xyz").respond(200)
        await alerts.evaluate_all(state)
        await run_jobs(state)
        assert (
            slack.call_count == 1 and "FIRING" in json.loads(slack.calls[0].request.content)["text"]
        )
    assert sent[0] == "smtp.example.test" and "FIRING" in sent[1]


async def test_private_webhook_url_is_refused(client, state, sm, monkeypatch):
    async def private(_h: str) -> list[str]:
        return ["10.0.0.5"]

    monkeypatch.setattr(alerts, "resolve", private)
    _, slo = await breached_slo(client, sm)
    ch = await webhook_channel(client, state)
    await breach_rule(client, slo, [ch])
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(HOOK_URL).respond(200)
        await alerts.evaluate_all(state)
        await run_jobs(state)
        assert route.call_count == 0
