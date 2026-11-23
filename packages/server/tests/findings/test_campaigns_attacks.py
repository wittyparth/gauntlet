"""Campaign expansion rules, attack routes, taxonomy and the markdown export."""

from __future__ import annotations

import pytest
from atk_helpers import add_finding, attack, benign, make_version, store_scenario, turn_attack
from gauntlet_core.schema import Attack
from gauntlet_server.services.attack_lib import upsert_attacks

pytestmark = pytest.mark.integration
LOCAL = "http://localhost:9/v1"


async def prime(client, state, *attacks):
    version = await make_version(client, LOCAL)
    await store_scenario(state, benign())
    async with state.sm() as s, s.begin():
        await upsert_attacks(s, "ws_test", list(attacks))
    return version


def body(version, **kw):
    return {
        "agent_version_id": version, "world_id": "ecommerce",
        "benign_scenario_ids": ["scn_benign_status"], "budget_usd_micros": 1_000_000, **kw,
    }  # fmt: skip


def needs(aid: str, req: str) -> Attack:
    return Attack.model_validate({**attack(aid).model_dump(mode="json"), "requires": [req]})


async def test_expansion_respects_capabilities_and_reports_skips(client, state):
    version = await prime(client, state, attack(), needs("atk_needs_mail", "tool:external_comm"))
    r = await client.post(
        "/v1/campaigns", json=body(version, attack_ids=["atk_dva_notes", "atk_needs_mail"])
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["attack_count"] == 1
    assert out["skipped"][0]["attack_id"] == "atk_needs_mail"
    assert "tool:external_comm" in out["skipped"][0]["reason"]
    assert out["run"]["counts"]["total"] == 1
    got = (await client.get(f"/v1/campaigns/{out['campaign_id']}")).json()
    assert got["progress"] == [] and got["run"]["purpose"] == "campaign"
    assert (await client.get("/v1/campaigns/run_nope")).status_code == 404


async def test_cap_is_a_seeded_deterministic_sample_and_mutations_add_variants(client, state):
    many = [attack(f"atk_many_{i:02d}") for i in range(8)]
    version = await prime(client, state, *many)
    ids = [a.id for a in many]

    async def chosen(seed: int, **kw) -> list[str]:
        r = await client.post(
            "/v1/campaigns",
            json=body(version, attack_ids=ids, seed=seed, **{"max_attacks": 3, **kw}),
        )
        assert r.status_code == 201, r.text
        run = r.json()["campaign_id"]
        eps = (await client.get(f"/v1/runs/{run}/episodes")).json()["items"]
        scns = [(await client.get(f"/v1/scenarios/{e['scenario_id']}")).json() for e in eps]
        await client.post(f"/v1/runs/{run}/cancel")
        return sorted(s["scenario"]["attack"]["attack"] for s in scns)

    a, b = await chosen(1), await chosen(1)
    assert a == b and len(a) == 3
    mutated = await chosen(1, mutations=["encode:base64"], max_attacks=100)
    assert len(mutated) == 16 and any("_m" in x for x in mutated)  # 8 originals + 8 variants


async def test_adaptive_unknown_category_and_scope_are_enforced(client, state):
    version = await prime(client, state, attack(), turn_attack())
    r = await client.post("/v1/campaigns", json=body(version, mode="adaptive"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "adaptive_unavailable"
    r = await client.post("/v1/campaigns", json=body(version, categories=["harmful_content"]))
    assert r.status_code == 422
    scope = (await client.get("/v1/settings/attack-scope")).json()
    await client.put(
        "/v1/settings/attack-scope", json={**scope, "allowed_categories": ["exfiltration"]}
    )
    r = await client.post("/v1/campaigns", json=body(version, attack_ids=["atk_dva_notes"]))
    assert r.status_code == 422 and r.json()["error"]["detail"]["key"] == "allowed_categories"
    await client.put("/v1/settings/attack-scope", json=scope)


async def test_remote_unverified_target_blocks_a_campaign(client, state):
    seed = await make_version(client, "https://agent.unverified.example/v1")
    await store_scenario(state, benign())
    async with state.sm() as s, s.begin():
        await upsert_attacks(s, "ws_test", [attack()])
    r = await client.post("/v1/campaigns", json=body(seed, attack_ids=["atk_dva_notes"]))
    assert r.status_code == 403 and r.json()["error"]["code"] == "target_not_verified"


async def test_attack_routes_import_is_idempotent_and_filters_work(client):
    first = (await client.post("/v1/attacks/import")).json()
    second = (await client.post("/v1/attacks/import")).json()
    assert first == second and first["imported"] >= 250 and first["by_source"]
    page = (await client.get("/v1/attacks?category=indirect_injection&limit=5")).json()
    assert 0 < len(page["items"]) <= 5
    assert all(a["category"] == "indirect_injection" for a in page["items"])
    aid = page["items"][0]["id"]
    assert (await client.get(f"/v1/attacks/{aid}")).json()["id"] == aid
    assert (await client.get("/v1/attacks/atk_nope")).status_code == 404
    docs = (await client.get("/v1/attacks?vector=document&limit=200")).json()["items"]
    assert docs and all(a["vector"] == "document" for a in docs)
    src = first["by_source"]
    name = next(iter(src))
    assert all(
        a["source"].startswith(name)
        for a in (await client.get(f"/v1/attacks?source={name}")).json()["items"]
    )
    plain = (await client.get("/v1/attacks?requires=tool:read&limit=200")).json()["items"]
    assert all(set(a["requires"]) <= {"tool:read"} for a in plain)
    tax = (await client.get("/v1/security/taxonomy")).json()
    assert len(tax["categories"]) == 17 and tax["verified_on"]


async def test_markdown_export_shape_and_payload_truncation(client, state):
    version = await make_version(client, LOCAL)
    long = attack().model_copy(update={"payload": "x" * 900 + " {{marker}}"})
    async with state.sm() as s, s.begin():
        await upsert_attacks(s, "ws_test", [long])
    fid = await add_finding(state, version, key="md1")
    md = (await client.get(f"/v1/findings/{fid}/export?format=md")).text
    assert md.startswith("# Refund via injected order note\n")
    for needle in (
        "- Severity: **high**", "OWASP LLM: LLM01", "Reproducibility: 1 of 1 attempts",
        "- Attack technique: note injection", "licence MIT", "[truncated]",
        "Dangerous-content categories are never stored",
    ):  # fmt: skip
        assert needle in md, needle
    assert "x" * 501 not in md
    js = (await client.get(f"/v1/findings/{fid}/export?format=json")).json()
    assert js["id"] == fid and js["episodes"] == []


def test_inject_target_override_applies_to_tool_result_attacks_without_a_target():
    from gauntlet_core.schema import Attack, WorldSpec
    from gauntlet_server.services.campaigns import with_default_target

    base = {
        "id": "atk_t", "title": "t", "category": "indirect_injection", "technique": "t",
        "source": "gauntlet-curated", "license": "MIT", "vector": "tool_result",
        "payload": "x {{marker}}", "objective": {"type": "tainted_call", "tool": "issue_refund"},
    }  # fmt: skip
    world = WorldSpec.model_validate(
        {"id": "w", "tools": [], "clock_start": "2026-01-01T00:00:00Z"}
    )
    got = with_default_target(Attack.model_validate(base), world, "orders/ord_1001/notes")
    assert got.target == "orders/ord_1001/notes"
    pinned = Attack.model_validate({**base, "target": "lookup_order"})
    assert with_default_target(pinned, world, "orders/ord_1001/notes").target == "lookup_order"
