"""Ownership verification: token flow, coverage, enforcement at run creation."""

from __future__ import annotations

import httpx
import pytest
from atk_helpers import make_attack_suite, make_version, run_body
from gauntlet_core.schema import AgentVersion
from gauntlet_core.targets import GuardedTransport, UrlPolicy
from gauntlet_server.services import ownership
from sqlalchemy import text

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def fake_net():
    records: dict[str, list[str]] = {}
    seen: list[httpx.Request] = []
    pages: dict[str, httpx.Response] = {}

    async def txt(name: str) -> list[str]:
        return records.get(name, [])

    class T(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return pages.get(str(request.url), httpx.Response(404))

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]  # a public address

    old = (ownership.DEPS.txt, ownership.DEPS.transport, ownership.DEPS.resolve)
    ownership.DEPS.txt, ownership.DEPS.transport, ownership.DEPS.resolve = txt, T(), resolve
    yield records, pages, seen
    ownership.DEPS.txt, ownership.DEPS.transport, ownership.DEPS.resolve = old


async def check(client, vid: str) -> dict:
    return (await client.post(f"/v1/targets/verifications/{vid}/check")).json()


async def test_dns_token_flow_verifies_and_gates_attack_runs(client, state, fake_net):
    records, _, _ = fake_net
    version = await make_version(client, "https://agent.victim.com/v1")
    suite = await make_attack_suite(client, state)
    r = await client.post("/v1/runs", json=run_body(suite, version))
    assert r.status_code == 403 and r.json()["error"]["code"] == "target_not_verified"
    assert r.json()["error"]["detail"]["host"] == "agent.victim.com"

    body = {"host": "victim.com", "method": "dns"}
    v = (await client.post("/v1/targets/verifications", json=body)).json()
    assert v["instructions"]["record_name"] == "_gauntlet-challenge.victim.com"
    assert (await check(client, v["id"]))["status"] == "failed"  # no record yet
    records["_gauntlet-challenge.victim.com"] = ["gauntlet-verify=wrong"]
    assert (await check(client, v["id"]))["status"] == "failed"
    records["_gauntlet-challenge.victim.com"] = [v["instructions"]["record_value"]]
    ok = await check(client, v["id"])
    assert ok["status"] == "verified" and ok["expires_at"]
    # the parent domain covers the subdomain host of the target
    r = await client.post("/v1/runs", json=run_body(suite, version))
    assert r.status_code == 201, r.text
    listed = (await client.get("/v1/targets/verifications")).json()["items"]
    assert [x["host"] for x in listed] == ["victim.com"]
    assert (await client.delete(f"/v1/targets/verifications/{v['id']}")).status_code == 204


async def test_http_method_does_not_follow_redirects_and_needs_exact_token(client, fake_net):
    _, pages, seen = fake_net
    body = {"host": "site.org", "method": "http"}
    v = (await client.post("/v1/targets/verifications", json=body)).json()
    url = f"https://site.org{ownership.WELL_KNOWN}"
    assert v["instructions"]["url"] == url
    pages[url] = httpx.Response(302, headers={"location": "https://evil.org/x"})
    assert (await check(client, v["id"]))["status"] == "failed"
    assert len(seen) == 1  # the redirect was not followed
    pages[url] = httpx.Response(200, text=f"{v['token']}\n")
    assert (await check(client, v["id"]))["status"] == "verified"


async def test_private_ip_blocked_by_ssrf_guard_and_bare_suffix_rejected(client):
    for host in ("com", "co.uk", "10.0.0.5"):
        r = await client.post("/v1/targets/verifications", json={"host": host, "method": "dns"})
        assert r.status_code == 422, host
        assert r.json()["error"]["code"] == "unverifiable_host"

    async def resolve(host: str) -> list[str]:
        return ["10.0.0.5"]

    t = GuardedTransport(httpx.AsyncHTTPTransport(), UrlPolicy(), resolve)
    with pytest.raises(Exception, match="private"):
        await t.handle_async_request(httpx.Request("GET", "https://internal.victim.com/x"))


async def test_expired_verification_no_longer_covers(client, state, fake_net):
    records, _, _ = fake_net
    version = await make_version(client, "https://a.expiring.io/v1")
    suite = await make_attack_suite(client, state)
    body = {"host": "expiring.io", "method": "dns"}
    v = (await client.post("/v1/targets/verifications", json=body)).json()
    records["_gauntlet-challenge.expiring.io"] = [v["instructions"]["record_value"]]
    await check(client, v["id"])
    async with state.sm() as s, s.begin():
        await s.execute(
            text("UPDATE target_verifications SET expires_at = now() - interval '1 day'")
        )
    r = await client.post("/v1/runs", json=run_body(suite, version))
    assert r.status_code == 403
    assert (await client.get("/v1/targets/verifications")).json()["items"][0]["status"] == "expired"


async def test_local_hosts_and_hosted_targets_are_exempt(client, state):
    suite = await make_attack_suite(client, state)
    for base in ("http://dva:8100/v1", "http://127.0.0.1:9/v1", "http://localhost:9/v1"):
        version = await make_version(client, base, label=base)
        r = await client.post("/v1/runs", json=run_body(suite, version))
        assert r.status_code == 201, (base, r.text)
        await client.post(f"/v1/runs/{r.json()['id']}/cancel")
    cfg = AgentVersion.model_validate(
        {
            "id": "a", "agent_id": "b", "label": "c", "profile": {"purpose": "x"},
            "target": {"kind": "hosted", "model": "m", "system_prompt": "s"},
        }
    ).target  # fmt: skip
    assert not ownership.is_remote(cfg, state.settings)
