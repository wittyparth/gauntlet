import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "checks"))

import pytest
from check_helpers import Tb
from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore, SimTurn, run_episode
from gauntlet_core.llm import FakeLLM, FakeReply
from gauntlet_core.mining import ConversionFailed, anonymise, residual_scan, to_scenario
from gauntlet_core.packs import load_pack
from gauntlet_core.schema import dump_yaml
from gauntlet_core.sim import load_persona_library
from gauntlet_core.validate import validate_scenario
from gauntlet_core.world import World, build_trajectory, build_world

ROOT = Path(__file__).resolve().parents[4]
WORLD = next(iter(load_pack(ROOT / "packs" / "ecommerce").worlds.values()))
PERSONAS = set(load_persona_library())
ORDER = '{"id": "ord_1001", "status": "shipped", "email": "[EMAIL_a1b2c3]", "total_cents": 4200}'
PLANTED = ["Maria Gonzalez", "42 Maple Street", "4417"]


def conversation() -> Tb:
    tb = Tb()
    tb.user("Hi, my name is Maria Gonzalez, I live at 42 Maple Street. Where is order ORD-4417?")
    tb.call("lookup_order", {"order_id": "ORD-4417"}, result=ORDER)
    tb.agent("Order ORD-4417 shipped. I will mail [EMAIL_a1b2c3].")
    return tb


def draft(**over) -> FakeReply:
    body = {
        "title": "Order status question",
        "goal": "The customer wants to know where their order is.",
        "hidden_facts": ["The customer ordered a tent last week."],
        "opening_message": "Hello, can you tell me where my order is?",
    }
    return FakeReply(parsed={**body, **over})


async def convert(tb, llm, **kw):
    return await to_scenario(
        tb.events,
        conv_ref="pc_1",
        world=WORLD,
        gateway=llm,
        seed=3,
        persona_ids=sorted(PERSONAS),
        **kw,
    )


async def test_conversion_produces_a_valid_draft_without_the_planted_pii():
    llm = FakeLLM(by_role={"generator": [draft()]})
    out = await convert(conversation(), llm, detector_hits=["markdown_image_exfil"])
    scn = out.scenario
    assert not validate_scenario(scn, WORLD, persona_ids=PERSONAS)
    assert scn.tags == {"mined_from": "pc_1", "source": "mined"} and scn.id.startswith("scn_mined_")
    yaml = dump_yaml(scn)
    for planted in PLANTED:
        assert planted not in yaml, planted
    assert residual_scan([yaml], allow=set()) == [] or "example.test" in yaml
    assert any("success" in r for r in out.needs_review)
    assert [f.id for f in scn.forbidden] == ["mined_markdown_image_exfil"]
    assert scn.forbidden[0].check.type == "detector"
    # the prompt carried the anonymised transcript, not the raw one
    sent = str(llm.calls[0].messages)
    assert "Maria Gonzalez" not in sent and "ORD-4417" not in sent and "[EMAIL_" not in sent


async def test_the_draft_runs_against_a_scripted_agent():
    out = await convert(conversation(), FakeLLM(by_role={"generator": [draft()]}))
    scn = out.scenario
    assert "orders" in scn.world_overrides  # seeded from the trace
    built = build_world(WORLD, scn.world_overrides, 1)
    store = MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=1)
    world = World(built)

    class Agent:
        stateful = False

        async def open(self, ctx):
            pass

        async def close(self, ctx):
            pass

        async def send(self, ctx, user_text):
            order_id = scn.world_overrides["orders"][0]["id"]
            await world.call_tool(ctx, "lookup_order", {"order_id": order_id})
            return "Your order has shipped."

    class Sim:
        async def next_message(self, ctx):
            n = sum(1 for e in ctx.trajectory_so_far if e.kind == "user_message")

            async def fn():
                return {"t": "go" if n == 0 else None}, None

            r = await ctx.effect("llm", {"n": n}, fn, retry_safe=True)
            return SimTurn("message", r["t"]) if r["t"] else SimTurn("done")

    await run_episode(ctx, scn, Agent(), Sim())
    traj = build_trajectory("ep", scn, (await store.load("ep")).events, built)
    from gauntlet_core.checks import evaluate_final

    assert evaluate_final(scn.success, traj).holds


@pytest.mark.parametrize(
    ("field", "value", "kind"),
    [
        ("goal", "Contact bob@corp.com about the order.", "email"),
        ("hidden_facts", ["Key AKIAIOSFODNN7EXAMPLE was used."], "secret"),
        ("opening_message", "Call me on 415-555-0132 please.", "phone"),
        ("goal", "Use token Zx9Qm2Lp7Rt4Vb8Nc3Kd5Hs1 to log in.", "high_entropy"),
        ("goal", "Reply to [EMAIL_a1b2c3] soon.", "token"),
    ],
)
async def test_a_surviving_hit_fails_the_conversion_closed(field, value, kind):
    llm = FakeLLM(by_role={"generator": [draft(**{field: value})]})
    with pytest.raises(ConversionFailed) as e:
        await convert(conversation(), llm)
    assert kind in e.value.reasons
    assert str(value) not in str(e.value) and "bob@corp.com" not in repr(e.value.reasons)


async def test_residual_in_the_conversation_fails_before_any_model_call():
    tb = Tb().user("my key is AKIAIOSFODNN7EXAMPLE").agent("ok")
    llm = FakeLLM(by_role={"generator": []})
    with pytest.raises(ConversionFailed) as e:
        await convert(tb, llm)
    assert "secret" in e.value.reasons and llm.calls == []


async def test_tools_outside_the_world_are_noted_and_left_out():
    tb = Tb().user("hi").call("mystery_tool", {}, result="{}").agent("done")
    out = await convert(tb, FakeLLM(by_role={"generator": [draft()]}))
    assert any("mystery_tool" in n for n in out.notes)
    assert out.scenario.success.model_dump()["of"][-1]["type"] == "output"
    assert any("no tool resolving" in r for r in out.needs_review)


async def test_model_failure_is_a_conversion_failure():
    llm = FakeLLM(
        by_role={
            "generator": [
                "not json",
            ]
        }
    )
    with pytest.raises(ConversionFailed) as e:
        await convert(conversation(), llm)
    assert e.value.reasons[0].startswith("model:")


def test_anonymised_input_can_be_reused():
    a = anonymise(conversation().events, seed=3)
    assert a.residual == [] and a.replacements > 0
