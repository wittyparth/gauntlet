from __future__ import annotations

import re

import pytest
from gauntlet_core.engine import (
    MemoryJournalStore,
    SimulatedCrash,
    dump_cassette,
    store_from_cassette,
)
from gauntlet_core.llm import FakeLLM, FakeReply
from gauntlet_core.llm.types import ProviderUnavailable
from gauntlet_core.runner import derive_episode_seed, execute_episode
from gauntlet_core.schema import Rubric
from rhelpers import (
    TARGET_ROLE,
    bad_script,
    call,
    deps,
    done,
    good_script,
    job,
    say,
    scenario,
    world_spec,
)


def kinds(events):
    return [e.kind for e in events]


async def test_good_agent_passes_bad_agent_fails_with_reasons():
    out = await execute_episode(job(), deps(FakeLLM(by_role=good_script())))
    assert (out.outcome, out.termination, out.reasons) == ("passed", "user_done", ())
    bad = await execute_episode(job(), deps(FakeLLM(by_role=bad_script())))
    assert bad.outcome == "failed" and bad.reasons == ("success", "no_cancel")


async def test_one_check_result_event_per_check_before_episode_ended():
    store = MemoryJournalStore()
    await execute_episode(job(), deps(FakeLLM(by_role=good_script()), store))
    events = (await store.load("ep_1")).events
    checks = [e for e in events if e.kind == "check_result"]
    assert [c.payload["check_id"] for c in checks] == ["success", "no_cancel"]
    assert checks[0].payload["holds"] is True and checks[1].payload["holds"] is False
    assert checks[1].payload["severity"] == "high" and checks[0].payload["severity"] is None
    assert kinds(events)[-1] == "episode_ended"
    assert events[-1].payload["outcome"] == "passed"


async def test_invalid_scenario_ends_without_any_llm_call():
    scn = scenario(success={"type": "tool_called", "tool": "no_such_tool"})
    llm = FakeLLM()
    store = MemoryJournalStore()
    out = await execute_episode(job(scn), deps(llm, store))
    assert out.outcome == "invalid_scenario" and "unknown_tool" in (out.detail or "")
    assert llm.calls == []
    assert kinds((await store.load("ep_1")).events) == ["episode_started", "episode_ended"]


def judge_script(result: str) -> FakeReply:
    def build(messages):
        text = messages[-1]["content"]
        seq = re.findall(r"\[(\d+)\] AGENT: ([^\n]+)", text)[-1]
        evidence = [{"seq": int(seq[0]), "quote": seq[1][:20]}] if result == "fail" else []
        return FakeReply(
            parsed={
                "reasoning": "r",
                "evidence": evidence,
                "result": result,
                "confidence": 0.95,
            }
        )

    return build  # type: ignore[return-value]


def hard_rubric(**kw) -> Rubric:
    base = {
        "id": "task_completion",
        "title": "t",
        "question": "q?",
        "pass_definition": "p",
        "fail_definition": "f",
        "severity": "medium",
        "hard_fail": True,
        "gating_allowed": True,
    }
    return Rubric.model_validate({**base, **kw})


async def test_judge_verdicts_are_events_before_episode_ended_and_hard_fail_flips():
    rub = hard_rubric()
    script = {**good_script(), "judge_small": [judge_script("fail")]}
    store = MemoryJournalStore()
    out = await execute_episode(job(rubrics={rub.id: rub}), deps(FakeLLM(by_role=script), store))
    events = (await store.load("ep_1")).events
    ks = kinds(events)
    assert ks.index("verdict") < ks.index("episode_ended")
    assert events[-1].payload["outcome"] == "failed"  # CQ-B13: the final, judged outcome
    assert out.outcome == "failed" and out.verdicts[0].result == "fail"
    pass_script = {**good_script(), "judge_small": [judge_script("pass")]}
    ok = await execute_episode(
        job(rubrics={rub.id: rub}, episode_id="ep_2"), deps(FakeLLM(by_role=pass_script))
    )
    assert ok.outcome == "passed" and ok.verdicts[0].result == "pass"


async def test_judge_stage_skipped_for_target_error_and_when_disabled():
    rub = hard_rubric()
    llm = FakeLLM(
        by_role={"simulator": [say("hi")], TARGET_ROLE: [FakeReply(error=ProviderUnavailable("x"))]}
    )
    out = await execute_episode(job(rubrics={rub.id: rub}), deps(llm))
    assert out.outcome == "target_error" and out.verdicts == []
    assert all(c.role != "judge_small" for c in llm.calls)
    llm2 = FakeLLM(by_role=good_script())
    out2 = await execute_episode(
        job(rubrics={rub.id: rub}, episode_id="ep_3"), deps(llm2, judge_enabled=False)
    )
    assert out2.outcome == "passed" and all(c.role != "judge_small" for c in llm2.calls)


async def test_simulated_world_fidelity_flagged():
    scn = scenario(
        success={"type": "tool_called", "tool": "carrier_status"}, forbidden=[], max_turns=3
    )
    script = {
        "simulator": [say("track it"), '{"status": "in transit"}', done()],
        TARGET_ROLE: [call("carrier_status", {}), "It is in transit."],
    }
    out = await execute_episode(
        job(scn, world=world_spec(llm_sim=True)), deps(FakeLLM(by_role=script))
    )
    assert out.outcome == "passed" and out.world_fidelity == "simulated"
    plain = await execute_episode(job(episode_id="ep_9"), deps(FakeLLM(by_role=good_script())))
    assert plain.world_fidelity == "full"


def remaining(script, effects):
    """Slice every role's script by how many of its llm effects are already recorded."""
    used: dict[str, int] = {}
    for rec in effects.values():
        if rec.kind == "llm" and rec.status == "done":
            role = rec.result["model"].removeprefix("fake/")
            used[role] = used.get(role, 0) + 1
    return {role: s[used.get(role, 0) :] for role, s in script.items()}


async def test_crash_at_every_append_then_resume_gives_identical_journal():
    rub = hard_rubric(hard_fail=False)
    script = {**good_script(), "judge_small": [judge_script("pass")]}
    clean = MemoryJournalStore()
    await execute_episode(job(rubrics={rub.id: rub}), deps(FakeLLM(by_role=script), clean))
    expected = [(e.kind, e.payload) for e in (await clean.load("ep_1")).events]
    for k in range(clean.appends):
        store = MemoryJournalStore()
        store.crash_before_append = k
        with pytest.raises(SimulatedCrash):
            await execute_episode(job(rubrics={rub.id: rub}), deps(FakeLLM(by_role=script), store))
        snap = await store.load("ep_1")
        store.crash_before_append = None
        epoch = store.bump_epoch("ep_1")
        resumed = FakeLLM(by_role=remaining(script, snap.effects))
        out = await execute_episode(job(rubrics={rub.id: rub}), deps(resumed, store), epoch=epoch)
        got = [(e.kind, e.payload) for e in (await store.load("ep_1")).events]
        assert got == expected, k
        assert out.outcome == "passed"


async def test_strict_cassette_replay_reproduces_identical_events():
    store = MemoryJournalStore()
    await execute_episode(job(), deps(FakeLLM(by_role=good_script()), store))
    snap = await store.load("ep_1")
    replay_store = await store_from_cassette(dump_cassette(snap), "ep_1")
    silent = FakeLLM()
    out = await execute_episode(job(), deps(silent, replay_store), replay_only=True)
    assert silent.calls == [] and out.outcome == "passed"
    assert [e.model_dump() for e in (await replay_store.load("ep_1")).events] == [
        e.model_dump() for e in snap.events
    ]


def test_derive_episode_seed_stable_and_distinct():
    a = derive_episode_seed(0, "s", 0)
    assert a == derive_episode_seed(0, "s", 0) and 0 <= a < 2**63
    assert len({derive_episode_seed(0, "s", r) for r in range(20)}) == 20
    assert derive_episode_seed(1, "s", 0) != a
