"""Nested effects (hard-cores 1.7a): spans, replay cursors, hooks, tail reload, abandon."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from gauntlet_core.engine import (
    EpisodeCtx,
    IndeterminateEffect,
    MemoryJournalStore,
    SimulatedCrash,
    StaleLease,
)
from gauntlet_core.schema import Cost, EffectRecord, EventDraft

EP = "ep_1"
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def ev(kind: str = "sim_note", **payload) -> EventDraft:
    return EventDraft(kind=kind, actor="platform", sim_time=T0, payload=payload)  # type: ignore[arg-type]


async def open_ctx(store: MemoryJournalStore) -> EpisodeCtx:
    return await EpisodeCtx.open(store, EP, run_id="r", rng_seed=1)


async def nested_outer(ctx: EpisodeCtx, calls: list[str]) -> dict:
    """An outer `target` effect whose fn runs two nested effects and emits events."""

    async def inner(tag: str):
        async def fn():
            calls.append(tag)
            return {"tag": tag}, Cost(usd_micros=3)

        return fn

    async def outer():
        calls.append("outer")
        await ctx.emit(ev(note="a"))
        await ctx.effect("tool", {"t": 1}, await inner("tool"), retry_safe=True)
        await ctx.emit(ev(note="b"))
        await ctx.effect("llm", {"t": 2}, await inner("llm"), retry_safe=True)
        return {"reply": "ok"}, None

    return await ctx.effect("target", {"x": 1}, outer, retry_safe=True)


async def test_span_recorded_on_the_outer_effect():
    store = MemoryJournalStore()
    ctx = await open_ctx(store)
    await nested_outer(ctx, [])
    j = await store.load(EP)
    assert j.effects["target:0"].span == {"events": 2, "ordinals": {"tool": 1, "llm": 1}}
    assert j.effects["tool:0"].span is None and j.effects["llm:0"].span is None
    assert [e.payload["note"] for e in j.events] == ["a", "b"]


async def test_replaying_a_done_outer_skips_fn_and_advances_cursors():
    store = MemoryJournalStore()
    await nested_outer(await open_ctx(store), [])
    store.bump_epoch(EP)
    ctx = await open_ctx(store)
    seen: list[list[str]] = []
    ctx.add_replay_hook(lambda events: seen.append([e.payload["note"] for e in events]))
    calls: list[str] = []
    out = await nested_outer(ctx, calls)
    assert out == {"reply": "ok"} and calls == []  # nothing ran
    assert seen == [["a", "b"]]
    assert len(ctx.trajectory_so_far) == 2
    # cursors advanced: the next effect of each kind gets the next ordinal, the next emit seq 2
    await ctx.effect("tool", {"n": 2}, _const({"v": 1}), retry_safe=True)
    await ctx.effect("llm", {"n": 2}, _const({"v": 1}), retry_safe=True)
    await ctx.emit(ev(note="c"))
    await ctx.flush()
    j = await store.load(EP)
    assert {"tool:1", "llm:1", "target:0"} <= set(j.effects)
    assert [e.seq for e in j.events] == [0, 1, 2]


def _const(value):
    async def fn():
        return value, None

    return fn


async def test_nested_work_by_another_process_is_counted_and_hooked():
    store = MemoryJournalStore()
    ctx = await open_ctx(store)
    hooked: list[int] = []
    ctx.add_replay_hook(lambda events: hooked.extend(e.seq for e in events))

    async def outer():
        # the api facade: a second ctx on the same journal, same epoch, appends while we wait
        other = await open_ctx(store)
        other.seek_end()
        await other.effect("tool", {"t": 1}, _const({"ok": True}), retry_safe=True)
        await other.emit(ev(note="from-facade"))
        await other.flush()
        return {"reply": "done"}, None

    await ctx.effect("target", {"x": 1}, outer, retry_safe=True, nested=True)
    j = await store.load(EP)
    assert j.effects["target:0"].span == {"events": 1, "ordinals": {"tool": 1}}
    assert hooked == [0]
    assert [e.payload["note"] for e in ctx.trajectory_so_far] == ["from-facade"]
    # our own next effect continues after the facade's ordinal and seq
    await ctx.effect("tool", {"t": 2}, _const({"ok": True}), retry_safe=True)
    await ctx.emit(ev(note="mine"))
    await ctx.flush()
    j = await store.load(EP)
    assert "tool:1" in j.effects and [e.seq for e in j.events] == [0, 1]


async def test_pending_outer_with_nested_records_is_indeterminate_even_if_retry_safe():
    store = MemoryJournalStore()
    ctx = await open_ctx(store)

    async def outer():
        await ctx.effect("tool", {"t": 1}, _const({"v": 1}), retry_safe=True)
        raise SimulatedCrash

    with pytest.raises(SimulatedCrash):
        await ctx.effect("target", {"x": 1}, outer, retry_safe=True)
    store.bump_epoch(EP)
    with pytest.raises(IndeterminateEffect):
        await _redo(store)


async def _redo(store):
    ctx = await open_ctx(store)

    async def outer():
        return {"reply": "again"}, None

    return await ctx.effect("target", {"x": 1}, outer, retry_safe=True)


async def test_pending_outer_without_nested_records_is_retried_when_retry_safe():
    store = MemoryJournalStore()
    ctx = await open_ctx(store)
    await ctx.flush(
        [EffectRecord(key="target:0", kind="target", request_hash=_h({"x": 1}), status="pending")]
    )
    store.bump_epoch(EP)
    assert await _redo(store) == {"reply": "again"}


def _h(request):
    from gauntlet_core.engine import request_hash

    return request_hash(request)


async def test_abandon_attempt_archives_and_restarts_the_journal():
    store = MemoryJournalStore()
    await nested_outer(await open_ctx(store), [])
    epoch = store.bump_epoch(EP)
    assert (await store.load(EP)).attempt == 0
    assert await store.abandon_attempt(EP, epoch) == 1
    j = await store.load(EP)
    assert j.events == [] and j.effects == {} and j.attempt == 1 and j.epoch == epoch
    assert len(store.archived(EP, 0).events) == 2 and "target:0" in store.archived(EP, 0).effects
    with pytest.raises(StaleLease):
        await store.abandon_attempt(EP, epoch + 5)
    # a fresh run starts at seq 0 again
    ctx = await EpisodeCtx.open(store, EP, run_id="r", rng_seed=1)
    await nested_outer(ctx, [])
    assert [e.seq for e in (await store.load(EP)).events] == [0, 1]
