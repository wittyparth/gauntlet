"""Failure clustering end to end: embeddings, named clusters with planted root causes, auto-run
threshold, idempotent re-run. Offline `HashEmbedder`; the models are FakeLLM scripts."""

from __future__ import annotations

import dataclasses
import json
import re
from collections import defaultdict

import pytest
from api_helpers import new_run
from gauntlet_core.llm import FakeLLM, FakeReply
from gauntlet_core.schema import Cost
from gauntlet_server.services.jobs import run_job
from gauntlet_server.services.runs import maybe_complete_run
from gauntlet_server.stores.jobs import PgJobQueue
from sqlalchemy import text

pytestmark = pytest.mark.integration

CAUSES = ["prompt_weakness", "missing_confirmation", "tool_error_unhandled"]


async def failing_families(client, sm, run_id: str, families: int = 3, reps: int = 4):
    """Mark `reps` episodes of each of `families` scenarios failed: planted failure families."""
    eps = (await client.get(f"/v1/runs/{run_id}/episodes", params={"limit": 200})).json()["items"]
    by_scn: dict[str, list[str]] = defaultdict(list)
    for e in eps:
        by_scn[e["scenario_id"]].append(e["id"])
    chosen = sorted(by_scn)[:families]
    ids = [i for s in chosen for i in by_scn[s][:reps]]
    async with sm() as s, s.begin():  # the demo suite fails one scenario on its own: start clean
        await s.execute(
            text("UPDATE episodes SET outcome = 'passed' WHERE run_id = :r"), {"r": run_id}
        )
        await s.execute(
            text("UPDATE episodes SET outcome = 'failed' WHERE id = ANY(:ids)"), {"ids": ids}
        )
    return chosen, ids


def scripted_models(chosen: list[str], titles: dict[str, str]):
    """judge_small names the cause by scenario title; generator names the cluster."""
    cause_of = {titles[s]: c for s, c in zip(chosen, CAUSES, strict=True)}

    def pick(messages):
        body = messages[-1]["content"]
        title = next(t for t in cause_of if t in body)
        return FakeReply(parsed={"cause": cause_of[title], "rationale": f"planted {title}"})

    def name(messages):
        body = messages[-1]["content"]
        title = next(t for t in cause_of if t in body)
        return FakeReply(
            parsed={
                "name": f"Failures in {title}",
                "description": "Planted failure family.",
                "suspected_cause": cause_of[title],
            }
        )

    return FakeLLM(by_role={"judge_small": [pick] * 40, "generator": [name] * 10})


async def titles_of(client, run_id: str) -> dict[str, str]:
    eps = (await client.get(f"/v1/runs/{run_id}/episodes", params={"limit": 200})).json()["items"]
    out = {}
    for sid in {e["scenario_id"] for e in eps}:
        out[sid] = (await client.get(f"/v1/scenarios/{sid}")).json()["scenario"]["title"]
    return out


async def run_queue(state) -> None:
    q = PgJobQueue(state.sm)
    for lease in await q.claim("test-worker", 10, 60):
        await run_job(state, q, lease)


async def test_three_planted_families_become_three_named_clusters_with_causes(client, state, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    run_id = await new_run(client, state, seed, repetitions=4)
    chosen, failed = await failing_families(client, sm, run_id)
    titles = await titles_of(client, run_id)
    assert len(set(titles[s] for s in chosen)) == 3
    state.settings = dataclasses.replace(state.settings, attribute_with_llm=True)
    state.gateway = scripted_models(chosen, titles)

    none = (await client.get(f"/v1/runs/{run_id}/clusters")).json()
    assert none == {"status": "none", "clusters": [], "unclustered": []}
    r = await client.post(f"/v1/runs/{run_id}/cluster")
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    queued = (await client.get(f"/v1/runs/{run_id}/clusters")).json()
    assert queued["status"] == "queued"
    await run_queue(state)
    job = (await client.get(f"/v1/jobs/{job_id}")).json()
    assert job["status"] == "done" and job["result"]["clusters"] == 3, job

    out = (await client.get(f"/v1/runs/{run_id}/clusters")).json()
    assert out["status"] == "done" and out["unclustered"] == []
    clusters = out["clusters"]
    assert len(clusters) == 3 and sorted(c["size"] for c in clusters) == [4, 4, 4]
    for c in clusters:
        (scn,) = c["scenario_ids"]
        want = CAUSES[chosen.index(scn)]
        assert c["root_cause"] == want and c["root_cause_share"] == 1.0
        assert c["name"] == " ".join(f"Failures in {titles[scn]}".split()[:6])  # six words
        assert c["description"]
        assert c["exemplar_episode_id"] in c["episode_ids"] and c["max_severity"]
        assert set(c["episode_ids"]) <= set(failed)

    async with sm() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT count(*), min(vector_dims(embedding)), max(vector_dims(embedding)) "
                    "FROM failure_embeddings WHERE run_id = :r"
                ),
                {"r": run_id},
            )
        ).one()
    assert tuple(rows) == (12, 1536, 1536)


async def test_manual_route_replaces_clusters_and_is_idempotent(client, state, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    run_id = await new_run(client, state, seed, repetitions=4)
    chosen, _ = await failing_families(client, sm, run_id)
    state.settings = dataclasses.replace(state.settings, attribute_with_llm=True)
    state.gateway = scripted_models(chosen, await titles_of(client, run_id))
    await client.post(f"/v1/runs/{run_id}/cluster")
    await run_queue(state)
    first = (await client.get(f"/v1/runs/{run_id}/clusters")).json()["clusters"]
    state.gateway = scripted_models(chosen, await titles_of(client, run_id))
    await client.post(f"/v1/runs/{run_id}/cluster")
    await run_queue(state)
    second = (await client.get(f"/v1/runs/{run_id}/clusters")).json()["clusters"]
    assert len(second) == 3 and {c["id"] for c in first}.isdisjoint({c["id"] for c in second})
    assert [(c["name"], c["episode_ids"]) for c in second] == [
        (c["name"], c["episode_ids"]) for c in first
    ]
    async with sm() as s:
        n = (await s.execute(text("SELECT count(*) FROM failure_clusters"))).scalar()
        e = (await s.execute(text("SELECT count(*) FROM failure_embeddings"))).scalar()
    assert (n, e) == (3, 12)


async def test_cluster_names_fall_back_when_naming_fails(client, state, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    run_id = await new_run(client, state, seed, repetitions=4)
    await failing_families(client, sm, run_id)
    state.gateway = FakeLLM(by_role={"judge_small": [], "generator": []})  # every call raises
    await client.post(f"/v1/runs/{run_id}/cluster")
    await run_queue(state)
    out = (await client.get(f"/v1/runs/{run_id}/clusters")).json()
    assert len(out["clusters"]) == 3
    assert all(re.match(r"Cluster \d+: ", c["name"]) for c in out["clusters"])
    assert all(c["root_cause"] == "unknown" for c in out["clusters"])


async def test_run_must_be_complete_and_owned(client):
    assert (await client.post("/v1/runs/run_nope/cluster")).status_code == 404
    assert (await client.get("/v1/runs/run_nope/clusters")).status_code == 404


async def jobs_of(sm, run_id: str) -> int:
    async with sm() as s:
        return int(
            (
                await s.execute(
                    text(
                        "SELECT count(*) FROM jobs WHERE kind = 'cluster' "
                        "AND payload->>'run_id' = :r"
                    ),
                    {"r": run_id},
                )
            ).scalar()
            or 0
        )


@pytest.mark.parametrize(("failures", "queued"), [(4, 0), (5, 1)])
async def test_auto_cluster_starts_only_from_five_failures(client, state, sm, failures, queued):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    run_id = await new_run(client, state, seed, repetitions=1)
    eps = (await client.get(f"/v1/runs/{run_id}/episodes")).json()["items"]
    async with sm() as s, s.begin():
        await s.execute(
            text("UPDATE episodes SET outcome = 'failed' WHERE id = ANY(:ids)"),
            {"ids": [e["id"] for e in eps[:failures]]},
        )
        await s.execute(text("UPDATE runs SET status = 'running', finished_at = NULL"))
    assert await jobs_of(sm, run_id) == 0
    async with sm() as s, s.begin():
        assert await maybe_complete_run(s, run_id, auto_cluster_min=state.settings.auto_cluster_min)
    assert await jobs_of(sm, run_id) == queued
    assert json.dumps(state.settings.auto_cluster_min) == "5"


def priced_cause(messages):
    return FakeReply(
        parsed={"cause": "prompt_weakness", "rationale": "x"}, cost=Cost(usd_micros=1500)
    )


def priced_name(messages):
    return FakeReply(
        parsed={"name": "N", "description": "d", "suspected_cause": "prompt_weakness"},
        cost=Cost(usd_micros=700),
    )


async def test_llm_attribution_is_off_by_default_and_charged_when_on(client, state, sm):
    from gauntlet_server.config import Settings

    assert Settings().attribute_with_llm is False
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    run_id = await new_run(client, state, seed, repetitions=4)
    await failing_families(client, sm, run_id)
    spent = "SELECT spent_usd_micros FROM runs WHERE id = :r"
    async with sm() as s:
        before = (await s.execute(text(spent), {"r": run_id})).scalar()
    state.settings = dataclasses.replace(state.settings, attribute_with_llm=True)
    state.gateway = FakeLLM(
        by_role={"judge_small": [priced_cause] * 40, "generator": [priced_name] * 10}
    )
    job_id = (await client.post(f"/v1/runs/{run_id}/cluster")).json()["job_id"]
    await run_queue(state)
    result = (await client.get(f"/v1/jobs/{job_id}")).json()["result"]
    assert result["cost_usd_micros"] > 0, result
    async with sm() as s:
        after = (await s.execute(text(spent), {"r": run_id})).scalar()
    assert after - before == result["cost_usd_micros"]
