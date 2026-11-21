import os
from pathlib import Path

from check_helpers import scenario
from gauntlet_core.eval import EpisodeRecord, aggregate_run
from gauntlet_core.eval.compare import (
    CompareParams,
    CompareReport,
    CostDelta,
    Flip,
    LatencyDelta,
)
from gauntlet_core.eval.pr_comment import MARKER, FindingBrief, render_pr_comment
from gauntlet_core.gates import GateConfig, evaluate_gates

GOLDEN = Path(__file__).parent / "golden"
URL = "https://gauntlet.example/runs/run_1"
SCN = {"a": scenario().model_copy(update={"id": "a", "title": "Refund flow"})}


def report(outcomes):
    eps = [
        EpisodeRecord(f"e{i}", "a", i, o, None, 1000, 900 + i, "full")
        for i, o in enumerate(outcomes)
    ]
    return aggregate_run("run_1", eps, {}, SCN, seed=1)


def compare(verdict, flips=()):
    return CompareReport(
        run_id="run_1",
        baseline_id="run_0",
        suite_id="s",
        margin=0.02,
        verdict=verdict,
        delta=-0.25 if verdict == "regression" else 0.0,
        ci_low=-0.4,
        ci_high=-0.1,
        p_value=0.01,
        detectable_effect_text=None,
        shared_scenarios=1,
        only_in_run=[],
        only_in_baseline=[],
        flips=list(flips),
        dimension_deltas=[],
        cost=CostDelta(
            baseline_per_episode_usd_micros=900, run_per_episode_usd_micros=1000, delta_pct=11.11
        ),
        latency=LatencyDelta(p50_baseline_ms=1, p50_run_ms=1, p95_baseline_ms=1, p95_run_ms=1),
        cautions=[],
        params=CompareParams(resamples=1, seed=1),
    )


def flip(i):
    return Flip(
        scenario_id=f"s{i}",
        title=f"Scenario {i} | pipes",
        status="newly_failing",
        rate_baseline=1.0,
        rate_run=0.0,
        n_baseline=3,
        n_run=3,
        episode_run=f"ep_{i}",
    )


def check_golden(name: str, text: str):
    path = GOLDEN / f"pr_comment_{name}.md"
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(text)
    assert text == path.read_text()


def test_golden_pass():
    rep = report(["passed"] * 5)
    gate = evaluate_gates(GateConfig(), rep, compare("no_detectable_change"))
    text = render_pr_comment(rep, compare("no_detectable_change"), gate, URL)
    assert text.splitlines()[0] == MARKER and "## Gauntlet: PASS" in text
    check_golden("pass", text)


def test_golden_fail_lists_newly_failing_and_findings():
    rep = report(["passed", "failed", "failed", "passed"])
    cmp = compare("regression", [flip(1), flip(2)])
    gate = evaluate_gates(GateConfig(), rep, cmp)
    text = render_pr_comment(
        rep, cmp, gate, URL, findings=[FindingBrief("Canary leaked", "critical")]
    )
    assert "## Gauntlet: FAIL" in text and "Newly failing scenarios (2)" in text
    assert f"{URL}/episodes/ep_1" in text and "critical: Canary leaked" in text
    assert "Scenario 1 \\| pipes" in text
    check_golden("fail", text)


def test_golden_error():
    rep = report(["budget_exhausted"])
    gate = evaluate_gates(GateConfig(), rep, run_status="budget_exhausted")
    text = render_pr_comment(rep, None, gate, URL)
    assert "## Gauntlet: ERROR" in text
    check_golden("error", text)


def test_truncation_keeps_markdown_valid_and_under_cap():
    rep = report(["passed", "failed"])
    cmp = compare("regression", [flip(i) for i in range(400)])
    gate = evaluate_gates(GateConfig(), rep, cmp)
    full = render_pr_comment(rep, cmp, gate, URL)
    assert full.count("- `s") == 10 and "and 390 more (truncated)" in full
    small = render_pr_comment(rep, cmp, gate, URL, max_chars=1000)
    assert len(small) <= 1000
    assert small.splitlines()[0] == MARKER
    assert small.count("```") % 2 == 0 and small.rstrip().endswith("</details>")
    assert "- `s" not in small


def test_json_block_cut_when_nothing_else_fits():
    rep = report(["passed", "failed"])
    gate = evaluate_gates(GateConfig(), rep)
    base = len(render_pr_comment(rep, None, gate, URL, max_chars=10**6))
    text = render_pr_comment(rep, None, gate, URL, max_chars=base - 100)
    assert len(text) <= base - 100 and "(truncated)" in text
    assert text.count("```") % 2 == 0 and text.rstrip().endswith("</details>")


def test_no_emoji_or_non_ascii():
    rep = report(["passed"] * 3)
    text = render_pr_comment(rep, None, evaluate_gates(GateConfig(), rep), URL)
    assert text.isascii()
