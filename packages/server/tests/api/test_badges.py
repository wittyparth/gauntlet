"""README badges: bands, no data, escaping, caching, revocation, rate limit, findings delta."""

from __future__ import annotations

import httpx
import pytest
from api_helpers import new_run
from gauntlet_server.app import create_app
from gauntlet_server.services.badges import AMBER, GREEN, GREY, RED, clean, render_svg
from sqlalchemy import text

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def fresh_rate_limit(state):
    async def wipe():
        async for key in state.redis.scan_iter("badge:rl:*"):
            await state.redis.delete(key)

    await wipe()
    yield
    await wipe()


@pytest.fixture
async def anon(state):
    """A client without credentials: the badge route must not need them."""
    transport = httpx.ASGITransport(app=create_app(state))
    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as c:
        yield c


async def badge_for(client, agent_id: str) -> dict:
    r = await client.post(f"/v1/agents/{agent_id}/badge")
    assert r.status_code == 201, r.text
    return r.json()


async def seeded_badge(client):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    agent = (await client.get(f"/v1/agents/{seed['agent_id']}")).json()["id"]
    return seed, await badge_for(client, agent)


async def set_pass_count(sm, run_id: str, passed: int) -> None:
    async with sm() as s, s.begin():
        await s.execute(
            text("UPDATE episodes SET outcome = 'failed' WHERE run_id = :r"), {"r": run_id}
        )
        await s.execute(
            text(
                "UPDATE episodes SET outcome = 'passed' WHERE id IN "
                "(SELECT id FROM episodes WHERE run_id = :r ORDER BY id LIMIT :n)"
            ),
            {"r": run_id, "n": passed},
        )


def path_of(url: str) -> str:
    return "/" + url.split("/", 3)[3]


async def test_create_returns_token_url_and_markdown(client):
    _, b = await seeded_badge(client)
    assert b["token"].startswith("gb_") and b["url"].endswith(f"/badge/{b['token']}.svg")
    assert b["markdown"] == f"![gauntlet]({b['url']})"
    assert (await client.post("/v1/agents/agent_nope/badge")).status_code == 404


@pytest.mark.parametrize(
    ("passed", "colour", "prefix"), [(10, GREEN, "100%"), (8, AMBER, "80%"), (5, RED, "50%")]
)
async def test_colour_bands_and_value(client, anon, sm, passed, colour, prefix):
    seed, b = await seeded_badge(client)
    await set_pass_count(sm, seed["run_id"], passed)
    r = await anon.get(path_of(b["url"]))
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")
    assert colour in r.text and f"{prefix} ±" in r.text and ">gauntlet<" in r.text


async def test_value_is_point_estimate_and_half_width_in_whole_points(client, anon, sm):
    seed, b = await seeded_badge(client)
    await set_pass_count(sm, seed["run_id"], 9)
    rep = (await client.get(f"/v1/runs/{seed['run_id']}/report")).json()
    half = round((rep["ci_high"] - rep["ci_low"]) / 2 * 100)
    r = await anon.get(path_of(b["url"]))
    assert f"{round(rep['pass_rate'] * 100)}% ±{half}" in r.text


async def test_no_data_is_grey(client, anon):
    agent = await client.post("/v1/agents", json={"project_id": "proj_1", "name": "N"})
    if agent.status_code != 201:  # projects come from the seed
        seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
        agent = await client.post(
            "/v1/agents", json={"project_id": seed["project_id"], "name": "N"}
        )
    b = await badge_for(client, agent.json()["id"])
    r = await anon.get(path_of(b["url"]))
    assert r.status_code == 200 and "no data" in r.text and GREY in r.text
    r = await anon.get(path_of(b["url"]), params={"metric": "security"})
    assert "no data" in r.text and "security" in r.text


async def test_security_metric_shows_the_grade_letter_only_when_attacks_ran(client, anon, sm):
    seed, b = await seeded_badge(client)
    r = await anon.get(path_of(b["url"]), params={"metric": "security"})
    assert "no data" in r.text  # the demo suite ran no attacks
    ver = seed["agent_version_id"]
    async with sm() as s, s.begin():
        eps = (await s.execute(text("SELECT id FROM episodes LIMIT 1"))).scalar()
        await s.execute(
            text(
                "INSERT INTO episode_attacks (episode_id, workspace_id, attack_id, category, "
                "vector, objective_held) VALUES (:e, 'ws_test', 'atk', 'indirect_injection', "
                "'document', false)"
            ),
            {"e": eps},
        )
    assert ver
    r = await anon.get(path_of(b["url"]), params={"metric": "security"})
    assert r.status_code == 200
    assert any(f">{g}<" in r.text for g in "ABCDF") and "no data" not in r.text


def test_hostile_text_cannot_reach_the_svg():
    svg = render_svg('<script>alert(1)</script>"', "9±3</text><g onload=x>", "#123456")
    assert "<script" not in svg and "alert(1)" not in svg.replace("alert1", "")
    assert "onload" in svg  # letters survive...
    assert "<g onload" not in svg and "</text><g" not in svg  # ...but the markup does not
    assert clean("a<b>&\"';c%± 9") == "abc%± 9"
    assert svg.count("<text") == 2


async def test_headers_etag_and_conditional_get(client, anon):
    _, b = await seeded_badge(client)
    path = path_of(b["url"])
    r = await anon.get(path)
    assert r.headers["cache-control"] == "public, max-age=300" and r.headers["etag"]
    again = await anon.get(path, headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304 and again.content == b""


async def test_unknown_and_revoked_tokens_get_a_grey_invalid_badge(client, anon):
    _, b = await seeded_badge(client)
    gone = await anon.get("/badge/gb_nope.svg")
    assert gone.status_code == 404 and "invalid" in gone.text and GREY in gone.text
    rotated = await client.post(
        f"/v1/agents/{(await client.get('/v1/agents')).json()['items'][0]['id']}/badge"
    )
    assert rotated.status_code == 201 and rotated.json()["token"] != b["token"]
    old = await anon.get(path_of(b["url"]))
    assert old.status_code == 404 and "invalid" in old.text
    new = await anon.get(path_of(rotated.json()["url"]))
    assert new.status_code == 200 and "invalid" not in new.text
    assert old.headers["cache-control"] == "no-store"


async def test_per_ip_rate_limit_is_60_a_minute(client, anon):
    _, b = await seeded_badge(client)
    path = path_of(b["url"])
    codes = [(await anon.get(path)).status_code for _ in range(62)]
    assert codes[:60] == [200] * 60 and codes[60:] == [429, 429]


async def test_the_badge_leaks_nothing_beyond_the_string(client, anon):
    seed, b = await seeded_badge(client)
    text_ = (await anon.get(path_of(b["url"]))).text
    for secret in (seed["run_id"], seed["agent_version_id"], seed["suite_id"], "ws_test"):
        assert secret not in text_


async def test_findings_delta_new_versus_baseline_version(client, state, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    base_run = seed["run_id"]
    agent_id = (await client.get("/v1/agents")).json()["items"][0]["id"]
    v2 = await client.post(
        f"/v1/agents/{agent_id}/versions",
        json={
            "label": "v2",
            "target": {"kind": "hosted", "model": "m", "system_prompt": "You help with orders."},
            "profile": {"purpose": "orders"},
            "world_id": "ecommerce",
        },
    )
    assert v2.status_code == 201, v2.text
    cand = await new_run(client, state, seed, agent_version_id=v2.json()["id"])
    eps = (await client.get(f"/v1/runs/{cand}/episodes")).json()["items"]

    async def finding(fid: str, version: str, attack: str, sev: str, episode: str | None):
        async with sm() as s, s.begin():
            await s.execute(
                text(
                    "INSERT INTO findings (id, workspace_id, agent_version_id, category, severity,"
                    " dedup_key, title, attack_id, doc) VALUES (:id, 'ws_test', :v, 'inj', :sev, "
                    ":id, :t, :a, '{}'::jsonb)"
                ),
                {"id": fid, "v": version, "sev": sev, "t": f"t {fid}", "a": attack},
            )
            if episode:
                await s.execute(
                    text("INSERT INTO finding_episodes (finding_id, episode_id) VALUES (:f, :e)"),
                    {"f": fid, "e": episode},
                )

    base_version = seed["agent_version_id"]
    await finding("fnd_old", base_version, "atk_known", "high", None)
    await finding("fnd_known", v2.json()["id"], "atk_known", "high", eps[0]["id"])
    await finding("fnd_new", v2.json()["id"], "atk_fresh", "critical", eps[1]["id"])
    r = await client.get(f"/v1/runs/{cand}/findings-delta", params={"baseline": base_run})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["new_by_severity"] == {"critical": 1}
    assert [f["id"] for f in out["new"]] == ["fnd_new"]
    assert (await client.get(f"/v1/runs/{cand}/findings-delta")).status_code == 404
