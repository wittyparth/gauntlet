"""Strict and agent_live replay of seeded episodes."""

from __future__ import annotations

import json

import pytest
from api_helpers import drain
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def seeded(client) -> dict:
    return (await client.post("/v1/dev/seed", json={"reset": False})).json()


async def test_strict_replay_is_identical_for_a_produced_episode(client):
    seed = await seeded(client)
    r = await client.post(
        f"/v1/episodes/{seed['failed_episode_id']}/replay", json={"mode": "strict"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["identical"] is True, body["divergence"]
    assert body["divergence"] is None and body["events"] > 5
    assert body["run_id"] is None


async def test_strict_replay_reports_a_tampered_effect_as_divergence(client, sm):
    seed = await seeded(client)
    ep = seed["failed_episode_id"]
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "UPDATE effects SET result = CAST(replace(result::text, 'refunded', 'declined') "
                "AS jsonb) WHERE episode_id = :e AND result::text LIKE '%refunded%'"
            ),
            {"e": ep},
        )
    r = await client.post(f"/v1/episodes/{ep}/replay", json={"mode": "strict"})
    body = r.json()
    assert r.status_code == 200 and body["identical"] is False
    assert body["divergence"]["seq"] >= 0 and body["divergence"]["expected"] is not None


async def test_replay_unknown_and_unfinished_episodes(client, sm):
    assert (
        await client.post("/v1/episodes/nope/replay", json={"mode": "strict"})
    ).status_code == 404
    seed = await seeded(client)
    async with sm() as s, s.begin():
        await s.execute(
            text("UPDATE episodes SET status = 'queued' WHERE id = :e"),
            {"e": seed["failed_episode_id"]},
        )
    r = await client.post(
        f"/v1/episodes/{seed['failed_episode_id']}/replay", json={"mode": "agent_live"}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "episode_not_done"


async def test_agent_live_replay_preloads_the_journal_and_runs_with_zero_model_calls(
    client, state, sm
):
    seed = await seeded(client)
    ep = seed["failed_episode_id"]
    r = await client.post(
        f"/v1/episodes/{ep}/replay",
        json={"mode": "agent_live", "budget_usd_micros": 500_000},
    )
    assert r.status_code == 201, r.text
    out = r.json()
    run = (await client.get(f"/v1/runs/{out['run_id']}")).json()
    assert run["purpose"] == "replay" and run["status"] == "queued"
    assert run["budget_usd_micros"] == 500_000 and run["counts"]["total"] == 1
    async with sm() as s:
        loaded = (
            await s.execute(
                text("SELECT count(*) FROM events WHERE episode_id = :e"), {"e": out["episode_id"]}
            )
        ).scalar()
        effects = (
            (
                await s.execute(
                    text("SELECT DISTINCT kind FROM effects WHERE episode_id = :e"),
                    {"e": out["episode_id"]},
                )
            )
            .scalars()
            .all()
        )
    assert loaded and set(effects) == {"llm", "tool"}  # the recording, minus target effects
    await drain(state, out["run_id"])
    done = (await client.get(f"/v1/episodes/{out['episode_id']}")).json()
    original = (await client.get(f"/v1/episodes/{ep}")).json()
    assert done["status"] == "done" and done["outcome"] == original["outcome"]
    # the same agent version: nothing diverged, the transcript is the recording's
    assert not [e for e in done["events"] if e["kind"] == "sim_note"]
    assert [e["payload"] for e in done["events"]] == [e["payload"] for e in original["events"]]
    assert done["cost_usd_micros"] == 0  # every effect was replayed


async def test_agent_live_with_a_changed_agent_diverges_and_records_where(client, state, sm):
    seed = await seeded(client)
    ep = seed["failed_episode_id"]
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO agent_versions (id, workspace_id, agent_id, label, config, world_id) "
                "SELECT 'agv_changed', workspace_id, agent_id, 'v2', "
                "jsonb_set(config, '{target,system_prompt}', "
                "to_jsonb('You are a new support assistant. ' "
                "|| (config->'target'->>'system_prompt'))), "
                "world_id FROM agent_versions WHERE id = :v"
            ),
            {"v": seed["agent_version_id"]},
        )
    r = await client.post(
        f"/v1/episodes/{ep}/replay", json={"mode": "agent_live", "agent_version_id": "agv_changed"}
    )
    assert r.status_code == 201, r.text
    out = r.json()
    await drain(state, out["run_id"])
    done = (await client.get(f"/v1/episodes/{out['episode_id']}")).json()
    notes = [
        e for e in done["events"]
        if e["kind"] == "sim_note" and e["payload"].get("kind") == "diverged"
    ]  # fmt: skip
    assert len(notes) == 1 and notes[0]["payload"]["first_live_seq"] == notes[0]["seq"]
    assert done["status"] == "done"
    assert json.dumps(notes[0]["payload"])
