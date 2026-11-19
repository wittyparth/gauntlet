"""The Phase 1 acceptance test: for every (flaw, scenario) pair of the catalog, the episode with
the flaw active fails a named check of the pack, and the same scripted user against the DVA
without flaws passes. Scripted brain, scripted user, no LLM."""

from __future__ import annotations

import pytest
from dva.flaws import FLAWS
from dva_helpers import load_script, pack, run_scenario, serving

PHASE1 = [f for f in FLAWS.values() if f.phase == 1]
PAIRS = [(f.id, s) for f in PHASE1 for s in f.detect_by]
SCENARIOS = sorted({s for _, s in PAIRS})
DETECTED: set[str] = set()


def test_pair_inventory():
    assert len(PHASE1) == 13
    assert len(PAIRS) == 28 and len(SCENARIOS) == 24
    assert {f.id for f in PHASE1} == {f"F{n:02d}" for n in range(1, 14)}
    assert all(s in pack().scenarios for _, s in PAIRS)


@pytest.mark.parametrize("scenario", SCENARIOS)
async def test_without_flaws_the_same_script_passes(scenario):
    script = load_script(scenario)
    async with serving(set()) as (url, facade):
        outcome, failing, replies = await run_scenario(scenario, script["turns"], url, facade)
    assert (outcome, failing) == ("passed", []), replies


@pytest.mark.parametrize(("flaw", "scenario"), PAIRS)
async def test_flaw_is_reachable_and_the_pack_check_detects_it(flaw, scenario):
    script = load_script(scenario)
    expected = set(script["flawed_reasons"][flaw])
    async with serving({flaw}) as (url, facade):
        outcome, failing, replies = await run_scenario(scenario, script["turns"], url, facade)
    assert outcome == "failed", replies
    assert expected & set(failing), (failing, replies)
    DETECTED.add(flaw)


def test_summary_flaws_detected(capsys):
    detected = {flaw for flaw, _ in PAIRS if flaw in DETECTED} or set()
    line = f"flaws detected: {len(detected)} of {len(PHASE1)} Phase 1 flaws"
    print(line)
    assert len(detected) == len(PHASE1), line
