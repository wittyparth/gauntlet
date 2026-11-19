"""World support for injections: marker discovery and tool-result injection documents."""

from datetime import UTC, datetime

from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore
from gauntlet_core.schema import DocumentSpec, StaticHandler, ToolSpec, WorldSpec
from gauntlet_core.world import World, build_world

MARK = "gmk-0123456789ab"


def spec(**kw) -> WorldSpec:
    tool = ToolSpec(
        name="read_page",
        description="d",
        risk="read",
        handler=StaticHandler(result={"title": "hi"}),
        untrusted_output=True,
    )
    return WorldSpec(tools=[tool], clock_start=datetime(2026, 1, 1, tzinfo=UTC), **kw)


def test_markers_are_discovered_in_documents_and_seed():
    s = spec(
        documents=[DocumentSpec(id="d", title="t", body=f"x {MARK} y", trusted=False)],
        seed={"orders": [{"id": "o1", "notes": "gmk-ffffffffffff"}]},
    )
    built = build_world(s, None, 1)
    assert set(built.markers) == {MARK, "gmk-ffffffffffff"}


async def test_inject_document_is_appended_to_tool_result_with_markers_in_origin():
    s = spec(
        documents=[DocumentSpec(id="inject:read_page", title="t", body=f"do {MARK}", trusted=False)]
    )
    built = build_world(s, None, 1)
    store = MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, "e", run_id="r", rng_seed=1)
    w = World(built)
    w.bind(ctx)
    res = await w.call_tool(ctx, "read_page", {})
    assert MARK in res.as_text() and "hi" in res.as_text()
    ev = next(e for e in ctx.trajectory_so_far if e.kind == "tool_result")
    assert ev.origin is not None and ev.origin.markers == [MARK]
