"""Cassette manifest, strict replay and agent_live replay of a real runner journal."""

from __future__ import annotations

import json

import pytest
from gauntlet_core.engine import MemoryJournalStore
from gauntlet_core.llm import FakeLLM, FakeReply
from gauntlet_core.replay import (
    CassetteError,
    CassetteManifest,
    export_cassette,
    first_live_seq,
    import_cassette,
    replay_agent_live,
    replay_strict,
    trajectory_from_cassette,
)
from gauntlet_core.runner import execute_episode
from gauntlet_core.schema import EffectRecord
from gauntlet_core.world import build_world
from rhelpers import (
    TARGET_ROLE,
    agent_version,
    bad_script,
    deps,
    done,
    good_script,
    job,
    persona,
)

SECRET = "sk-super-secret-value-123"


def manifest(**kw) -> CassetteManifest:
    j = job()
    return CassetteManifest(
        episode_id="ep_1",
        run_id="run_1",
        scenario=j.scenario,
        world=j.world,
        rng_seed=j.rng_seed,
        agent_version=agent_version(),
        persona=persona(),
        platform_version="test",
        **kw,
    )


async def produce(script=None) -> str:
    store = MemoryJournalStore()
    await execute_episode(job(), deps(FakeLLM(by_role=script or good_script()), store))
    return export_cassette(await store.load("ep_1"), manifest())


async def test_strict_replay_of_a_produced_journal_is_identical():
    text = await produce()
    rep = await replay_strict(text)
    assert rep.identical and rep.divergence is None and rep.events > 5


async def test_export_then_import_round_trips():
    text = await produce()
    snap, man = import_cassette(text)
    assert man.scenario.id == "scn_status" and man.world.id == "shop" and man.rng_seed == 11
    assert export_cassette(snap, man).splitlines()[1:] == text.splitlines()[1:]
    assert [e.seq for e in snap.events] == list(range(len(snap.events)))


async def test_manifest_rebuilds_the_trajectory_and_world_offline():
    snap, man = import_cassette(await produce())
    traj = trajectory_from_cassette(snap, man)
    built = build_world(man.world, man.scenario.world_overrides, man.rng_seed)
    assert built.initial == build_world(job().world, job().scenario.world_overrides, 11).initial
    assert traj.diff.changes == [] and [c.tool for c in traj.tool_calls()] == ["lookup_order"]
    bad_snap, bad_man = import_cassette(await produce(bad_script()))
    bt = trajectory_from_cassette(bad_snap, bad_man)
    assert [c.tool for c in bt.tool_calls()] == ["cancel_order"]


async def test_tampered_effect_result_reports_divergence_at_that_seq():
    snap, man = import_cassette(await produce())
    final_reply = next(
        k for k, r in snap.effects.items() if "Your order has shipped." in json.dumps(r.result)
    )
    rec = snap.effects[final_reply]
    snap.effects[final_reply] = rec.model_copy(
        update={"result": json.loads(json.dumps(rec.result).replace("has shipped", "is lost"))}
    )
    rep = await replay_strict(export_cassette(snap, man))
    assert not rep.identical and rep.divergence is not None
    assert rep.divergence.seq == next(e.seq for e in snap.events if e.kind == "agent_message")
    assert rep.divergence.expected == {"text": "Your order has shipped."}


async def test_any_live_call_in_strict_mode_is_reported_as_a_divergence():
    snap, man = import_cassette(await produce())
    drop = {k: v for k, v in snap.effects.items() if k != "llm:1"}  # the second sim turn
    snap.effects = drop
    rep = await replay_strict(export_cassette(snap, man))
    assert not rep.identical and rep.divergence is not None and rep.divergence.seq > 0


async def test_redaction_removes_planted_secrets():
    store = MemoryJournalStore()
    await execute_episode(job(), deps(FakeLLM(by_role=good_script()), store))
    snap = await store.load("ep_1")
    snap.effects["llm:0"] = EffectRecord(
        key="llm:0", kind="llm", request_hash="h", status="done",
        result={"leak": f"token {SECRET} here"},
    )  # fmt: skip
    text = export_cassette(snap, manifest(), secrets=[SECRET])
    assert SECRET not in text and "[REDACTED]" in text


async def test_import_validates_format_lines_and_manifest():
    with pytest.raises(CassetteError, match="format"):
        import_cassette(json.dumps({"t": "header", "format": "nope", "manifest": {}}))
    text = await produce()
    with pytest.raises(CassetteError) as exc:
        import_cassette(text + "not json\n")
    assert exc.value.line == len(text.splitlines()) + 1
    empty = json.dumps({"t": "header", "format": "gauntlet-cassette/1", "manifest": {}})
    with pytest.raises(CassetteError, match="manifest"):
        import_cassette(empty)
    with pytest.raises(CassetteError, match="no usable manifest"):
        import_cassette("")


async def test_import_rejects_gaps_in_seq_with_the_line_number():
    text = await produce()
    lines = text.splitlines()
    del lines[3]  # drop an event line: seq no longer dense
    with pytest.raises(CassetteError, match="seq"):
        import_cassette("\n".join(lines))


async def test_agent_live_replays_until_the_new_agent_diverges():
    text = await produce()
    snap, _ = import_cassette(text)
    changed = agent_version().model_copy(
        update={"target": agent_version().target.model_copy(update={"system_prompt": "Be brief."})}
    )
    llm = FakeLLM(
        by_role={
            TARGET_ROLE: [FakeReply(text="Let me not look that up.")],
            "simulator": [done()],  # the first simulator turn replays; only the second is live
        }
    )
    out, store = await replay_agent_live(text, changed, deps(llm), return_store=True)
    assert [c.role for c in llm.calls] == [TARGET_ROLE, "simulator"]
    events = (await store.load("ep_agent_live")).events
    notes = [e for e in events if e.kind == "sim_note" and e.payload.get("kind") == "diverged"]
    assert len(notes) == 1 and first_live_seq(events) == notes[0].seq == 2
    assert notes[0].payload["note"] == "llm:1"  # the agent's first model call: request changed
    assert [e.payload.get("text") for e in events if e.kind == "agent_message"] == [
        "Let me not look that up."
    ]
    assert out.outcome == "failed"  # the new agent never looked the order up

    # the same agent replays without a single model call
    llm2 = FakeLLM()
    out2, store2 = await replay_agent_live(text, agent_version(), deps(llm2), return_store=True)
    assert llm2.calls == [] and out2.outcome == "passed"
    assert first_live_seq((await store2.load("ep_agent_live")).events) is None
    assert len(snap.events) == len((await store2.load("ep_agent_live")).events)
