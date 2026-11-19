"""Nested effects end to end (hard-cores 1.7a): hosted target with tools, wired target through
LocalFacade, and an llm_sim tool. Each is crashed before every append and resumed; the final
journal must equal an uninterrupted run, and a strict cassette replay makes zero calls."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import httpx
import pytest
from gauntlet_core import runner
from gauntlet_core.engine import (
    IndeterminateEffect,
    MemoryJournalStore,
    SimulatedCrash,
    dump_cassette,
    store_from_cassette,
)
from gauntlet_core.llm import FakeLLM
from gauntlet_core.runner import execute_episode, execute_with_attempts
from gauntlet_core.schema import (
    AgentProfile,
    AgentVersion,
    Cost,
    OpenAICompatTargetConfig,
)
from gauntlet_core.targets import LocalFacade, UrlPolicy
from rhelpers import (
    MODEL,
    TARGET_ROLE,
    call,
    done,
    job,
    say,
    scenario,
    world_spec,
)

COST = Cost(usd_micros=10, input_tokens=1, output_tokens=1, model="fake")


class MemoGateway:
    """A deterministic model: the first time it sees a request it pops the next scripted reply
    for that role, afterwards it answers the same request the same way (temperature 0)."""

    def __init__(self, by_role: dict[str, list[Any]]) -> None:
        self._inner = FakeLLM(by_role=by_role, default_cost=COST)
        self._memo: dict[str, Any] = {}
        self.calls = 0

    async def complete(self, role, messages, *, tools=None, response_model=None, **kw):
        self.calls += 1
        key = json.dumps(
            [role, messages, tools, response_model.__name__ if response_model else None],
            sort_keys=True,
            default=str,
        )
        if key not in self._memo:
            self._memo[key] = await self._inner.complete(
                role, messages, tools=tools, response_model=response_model, **kw
            )
        return self._memo[key]

    def estimate_usd_micros(self, role, messages, *, max_output_tokens=None) -> int:
        return 0

    async def embed(self, role, texts):
        return await self._inner.embed(role, texts)


def fingerprint(snap):
    events = [(e.seq, e.kind, e.actor, e.payload, e.effect_key) for e in snap.events]
    effects = {
        k: (r.kind, r.status, r.request_hash, r.result, r.span, r.cost)
        for k, r in snap.effects.items()
    }
    return events, effects


def llm_sim_script():
    return {
        "simulator": [say("track it"), '{"status": "in transit"}', done()],
        TARGET_ROLE: [call("carrier_status", {}), "It is in transit."],
    }


def llm_sim_job():
    scn = scenario(
        success={"type": "tool_called", "tool": "carrier_status"}, forbidden=[], max_turns=3
    )
    return job(scn, world=world_spec(llm_sim=True))


def hosted_two_tools_script():
    return {
        "simulator": [say("where is ord_1, and cancel ord_2"), done()],
        TARGET_ROLE: [
            call("lookup_order", {"order_id": "ord_1"}, "a"),
            call("cancel_order", {"order_id": "ord_2", "status": "cancelled"}, "b"),
            "ord_1 shipped, ord_2 cancelled",
        ],
    }


def hosted_job():
    return job(scenario(forbidden=[]))


async def crash_matrix(make_job, make_deps, *, expect_attempt_ok: set[int]):
    """Run clean, then crash before each append and resume; return the clean fingerprint."""
    clean = MemoryJournalStore()
    out = await execute_episode(make_job(), make_deps(clean))
    assert out.outcome == "passed", out
    expected = fingerprint(await clean.load("ep_1"))
    attempts: list[int] = []
    for k in range(clean.appends):
        store = MemoryJournalStore()
        store.crash_before_append = k
        with pytest.raises(SimulatedCrash):
            await execute_episode(make_job(), make_deps(store))
        store.crash_before_append = None
        epoch = store.bump_epoch("ep_1")
        res = await execute_with_attempts(make_job(), make_deps(store), epoch=epoch)
        snap = await store.load("ep_1")
        assert res.outcome == "passed", k
        assert fingerprint(snap) == expected, f"crash point {k}"
        assert snap.attempt in expect_attempt_ok, f"crash point {k}: attempt {snap.attempt}"
        attempts.append(snap.attempt)
    return expected, attempts


async def strict_replay_is_free(make_job, make_deps, gateway_calls):
    store = MemoryJournalStore()
    await execute_episode(make_job(), make_deps(store))
    snap = await store.load("ep_1")
    replay = await store_from_cassette(dump_cassette(snap), "ep_1")
    before = gateway_calls()
    out = await execute_episode(make_job(), make_deps(replay), replay_only=True)
    assert out.outcome == "passed"
    assert gateway_calls() == before, "strict replay made calls"
    assert fingerprint(await replay.load("ep_1")) == fingerprint(snap)


# --------------------------------------------------------------------------- hosted + tools


async def test_hosted_with_tools_crash_matrix_and_zero_call_replay():
    script = hosted_two_tools_script()
    gw = MemoGateway(script)

    def deps(store):
        return runner.RunnerDeps(store=store, gateway=gw)

    (_, effects), attempts = await crash_matrix(hosted_job, deps, expect_attempt_ok={0})
    assert set(attempts) == {0}  # no nesting, so no abandoned attempt
    assert effects["tool:0"][4] is None  # hosted tool effects are top level: no span
    await strict_replay_is_free(hosted_job, deps, lambda: gw.calls)


# --------------------------------------------------------------------------- llm_sim tool


async def test_llm_sim_goes_through_llm_effect_nested_in_the_tool_effect():
    gw = MemoGateway(llm_sim_script())
    store = MemoryJournalStore()
    out = await execute_episode(llm_sim_job(), runner.RunnerDeps(store=store, gateway=gw))
    snap = await store.load("ep_1")
    span = snap.effects["tool:0"].span
    assert span == {"events": 0, "ordinals": {"llm": 1}}
    llm_costs = [r.cost.usd_micros for r in snap.effects.values() if r.kind == "llm" and r.cost]
    assert len(llm_costs) == 5 and all(c == 10 for c in llm_costs)  # sim, 2 target, llm_sim, sim
    assert out.cost.usd_micros == 50 and out.world_fidelity == "simulated"


async def test_llm_sim_crash_matrix_and_zero_call_replay():
    gw = MemoGateway(llm_sim_script())

    def deps(store):
        return runner.RunnerDeps(store=store, gateway=gw)

    # a crash inside the nested window abandons the attempt (1.7a rule 4); all others resume
    _, attempts = await crash_matrix(llm_sim_job, deps, expect_attempt_ok={0, 1})
    assert 1 in attempts and 0 in attempts
    await strict_replay_is_free(llm_sim_job, deps, lambda: gw.calls)


# --------------------------------------------------------------------------- wired + facade


def wired_version() -> AgentVersion:
    return AgentVersion(
        id="agv_w",
        agent_id="agt_1",
        label="wired",
        target=OpenAICompatTargetConfig(base_url="http://agent.test/v1", model=MODEL, wired=True),
        profile=AgentProfile(purpose="support", policies_text="R1."),
    )


class WiredHarness:
    def __init__(self) -> None:
        self.agent_hits = 0
        self.gw = MemoGateway({"simulator": [say("where is ord_1, cancel ord_2"), done()]})

    def deps(self, store):
        facade = LocalFacade(secret=b"s" * 32)

        async def agent(request: httpx.Request) -> httpx.Response:
            self.agent_hits += 1
            token = request.headers["x-gauntlet-episode"]
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=facade.app), base_url="http://facade"
            ) as c:
                r1 = await c.post(f"/mock/{token}/tools/lookup_order", json={"order_id": "ord_1"})
                await c.post(
                    f"/mock/{token}/tools/cancel_order",
                    json={"order_id": "ord_2", "status": "cancelled"},
                )
            status = r1.json()["result"]["status"]
            return httpx.Response(
                200, json={"choices": [{"message": {"content": f"ord_1 is {status}"}}]}
            )

        return runner.RunnerDeps(
            store=store,
            gateway=self.gw,
            http=httpx.AsyncClient(transport=httpx.MockTransport(agent)),
            url_policy=UrlPolicy(allow_private=True),
            facade=facade,
        )

    def job(self):
        return dataclasses.replace(hosted_job(), agent_version=wired_version())


async def test_wired_through_local_facade_crash_matrix_and_zero_call_replay():
    h = WiredHarness()
    (events, effects), attempts = await crash_matrix(h.job, h.deps, expect_attempt_ok={0, 1})
    assert 1 in attempts and 0 in attempts
    assert effects["target:0"][4] == {"events": 4, "ordinals": {"tool": 2}}
    final_orders = [e for e in events if e[1] == "tool_result"]
    assert len(final_orders) == 2
    hits = h.agent_hits
    await strict_replay_is_free(h.job, h.deps, lambda: (h.gw.calls, h.agent_hits))
    assert h.agent_hits == hits + 1  # only the non-replay clean run inside the helper called it


# --------------------------------------------------------------------------- attempt limit


async def test_three_indeterminate_attempts_end_as_platform_error(monkeypatch):
    seen: list[int] = []

    async def always_indeterminate(job, deps, *, epoch=0, replay_only=False):
        seen.append((await deps.store.load(job.episode_id)).attempt)
        raise IndeterminateEffect("ep_1 effect target:0")

    monkeypatch.setattr(runner, "execute_episode", always_indeterminate)
    store = MemoryJournalStore()
    epoch = store.bump_epoch("ep_1")
    out = await execute_with_attempts(
        hosted_job(), runner.RunnerDeps(store=store, gateway=FakeLLM()), epoch=epoch
    )
    assert seen == [0, 1, 2]
    assert out.outcome == "platform_error" and out.termination == "error"
    snap = await store.load("ep_1")
    assert snap.attempt == 2
    ended = [e for e in snap.events if e.kind == "episode_ended"]
    assert len(ended) == 1 and ended[0].payload["outcome"] == "platform_error"
