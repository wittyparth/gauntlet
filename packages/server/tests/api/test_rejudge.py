"""Rejudge: replaces the verdict rows of an evaluator set, never touches the journal."""

from __future__ import annotations

from typing import Any

import pytest
from gauntlet_core.llm import FakeLLM, FakeReply
from gauntlet_core.schema import Cost
from sqlalchemy import text

pytestmark = pytest.mark.integration

HARD = {
    "id": "rb_hard",
    "version": 1,
    "title": "Hard rule",
    "question": "Did the agent break the hard rule?",
    "pass_definition": "It did not.",
    "fail_definition": "It did.",
    "severity": "low",
    "hard_fail": True,
    "gating_allowed": True,
}


def verdict_reply(result: str, quote: tuple[int, str] | None = None, usd: int = 25) -> Any:
    ev = [{"seq": quote[0], "quote": quote[1]}] if quote else []
    return FakeReply(
        parsed={"reasoning": "because", "evidence": ev, "result": result, "confidence": 0.95},
        cost=Cost(usd_micros=usd),
    )


async def passed_episode(client) -> tuple[dict, str, tuple[int, str]]:
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    eps = (
        await client.get(f"/v1/runs/{seed['run_id']}/episodes", params={"outcome": "passed"})
    ).json()
    ep = eps["items"][0]["id"]
    detail = (await client.get(f"/v1/episodes/{ep}")).json()
    msg = next(e for e in detail["events"] if e["kind"] == "agent_message")
    return seed, ep, (msg["seq"], msg["payload"]["text"][:24])


async def rows(sm, ep: str) -> dict[str, str]:
    async with sm() as s:
        out = await s.execute(
            text("SELECT evaluator, id FROM verdicts WHERE episode_id = :e"), {"e": ep}
        )
        return {r[0]: r[1] for r in out}


async def events_count(sm, ep: str) -> int:
    async with sm() as s:
        return int(
            (
                await s.execute(
                    text("SELECT count(*) FROM events WHERE episode_id = :e"), {"e": ep}
                )
            ).scalar()
        )


async def test_replaces_only_the_named_evaluators_rows_and_adds_no_events(client, state, sm):
    _, ep, _ = await passed_episode(client)
    before, n_events = await rows(sm, ep), await events_count(sm, ep)
    assert "judge:task_completion" in before
    state.gateway = FakeLLM(by_role={"judge_small": [verdict_reply("pass")]})
    r = await client.post(f"/v1/episodes/{ep}/rejudge", json={"rubrics": ["task_completion"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert [v["criterion"] for v in out["verdicts"]] == ["task_completion"]
    assert out["cost_usd_micros"] == 25 and out["outcome_before"] == "passed"
    after = await rows(sm, ep)
    assert set(after) == set(before)
    assert after["judge:task_completion"] != before["judge:task_completion"]  # replaced
    assert all(after[k] == v for k, v in before.items() if k != "judge:task_completion")
    assert await events_count(sm, ep) == n_events  # the journal is untouched
    audit = (await client.get("/v1/audit")).json()["items"]
    assert any(a["action"] == "episode.rejudged" for a in audit)


async def test_a_hard_fail_verdict_flips_the_outcome_and_the_report_follows(client, state, sm):
    seed, ep, quote = await passed_episode(client)
    async with sm() as s, s.begin():
        await s.execute(
            text("INSERT INTO rubrics (id, version, workspace_id, doc) "
                 "VALUES ('rb_hard', 1, 'ws_test', CAST(:d AS jsonb))"),
            {"d": __import__("json").dumps(HARD)},
        )  # fmt: skip
    state.gateway = FakeLLM(by_role={"judge_small": [verdict_reply("fail", quote)]})
    r = await client.post(f"/v1/episodes/{ep}/rejudge", json={"rubrics": ["rb_hard"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["outcome_before"], out["outcome_after"]) == ("passed", "failed")
    assert out["verdicts"][0]["hard_fail"] is True
    detail = (await client.get(f"/v1/episodes/{ep}")).json()
    assert detail["outcome"] == "failed"
    assert any(v["criterion"] == "rb_hard" for v in detail["verdicts"])
    report = (await client.get(f"/v1/runs/{seed['run_id']}/report")).json()
    assert any(h == ep for h in report["hard_fail_episodes"])
    audit = (await client.get("/v1/audit")).json()["items"]
    entry = next(a for a in audit if a["action"] == "episode.rejudged")
    assert entry["detail"]["outcome_history"] == ["passed", "failed"]


async def test_cache_avoids_calls_and_force_bypasses_it(client, state):
    _, ep, _ = await passed_episode(client)
    llm = FakeLLM(by_role={"judge_small": [verdict_reply("pass"), verdict_reply("pass")]})
    state.gateway = llm
    body = {"rubrics": ["task_completion"]}
    first = await client.post(f"/v1/episodes/{ep}/rejudge", json=body)
    assert first.status_code == 200 and len(llm.calls) == 1 and first.json()["cost_usd_micros"] > 0
    second = await client.post(f"/v1/episodes/{ep}/rejudge", json=body)
    assert len(llm.calls) == 1 and second.json()["cost_usd_micros"] == 0  # cache hit
    forced = await client.post(f"/v1/episodes/{ep}/rejudge", json={**body, "force": True})
    assert forced.status_code == 200 and len(llm.calls) == 2


async def test_cost_is_attributed_to_the_run_and_a_spent_budget_refuses(client, state, sm):
    seed, ep, _ = await passed_episode(client)
    state.gateway = FakeLLM(by_role={"judge_small": [verdict_reply("pass", usd=40)]})
    async with sm() as s:
        spent = (
            await s.execute(
                text("SELECT spent_usd_micros FROM runs WHERE id = :r"), {"r": seed["run_id"]}
            )
        ).scalar()
    r = await client.post(f"/v1/episodes/{ep}/rejudge", json={"rubrics": ["task_completion"]})
    assert r.status_code == 200
    async with sm() as s:
        now = (
            await s.execute(
                text("SELECT spent_usd_micros FROM runs WHERE id = :r"), {"r": seed["run_id"]}
            )
        ).scalar()
    assert now == spent + 40
    async with sm() as s, s.begin():
        await s.execute(
            text("UPDATE runs SET spent_usd_micros = budget_usd_micros WHERE id = :r"),
            {"r": seed["run_id"]},
        )
    refused = await client.post(f"/v1/episodes/{ep}/rejudge", json={"rubrics": ["task_completion"]})
    assert refused.status_code == 402 and refused.json()["error"]["code"] == "budget_too_low"


async def test_unknown_episode_rubric_and_unfinished(client, state, sm):
    _, ep, _ = await passed_episode(client)
    assert (await client.post("/v1/episodes/nope/rejudge", json={})).status_code == 404
    missing = await client.post(f"/v1/episodes/{ep}/rejudge", json={"rubrics": ["nope"]})
    assert missing.status_code == 404
    async with sm() as s, s.begin():
        await s.execute(text("UPDATE episodes SET status = 'queued' WHERE id = :e"), {"e": ep})
    assert (await client.post(f"/v1/episodes/{ep}/rejudge", json={})).status_code == 409
