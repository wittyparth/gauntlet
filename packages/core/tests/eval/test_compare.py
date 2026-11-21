from check_helpers import scenario
from gauntlet_core.eval import EpisodeRecord, aggregate_run
from gauntlet_core.eval.compare import CompareReport, RunData, compare_runs

SCNS = {
    f"s{i:02d}": scenario().model_copy(update={"id": f"s{i:02d}", "title": f"Scenario {i}"})
    for i in range(20)
}


def episodes(prefix: str, rates: dict[str, list[bool]], cost=100, lat=1000):
    out = []
    for sid, trials in rates.items():
        for rep, ok in enumerate(trials):
            out.append(
                EpisodeRecord(
                    f"{prefix}_{sid}_{rep}",
                    sid,
                    rep,
                    "passed" if ok else "failed",
                    None,
                    cost,
                    lat,
                    "full",
                )
            )
    return out


def run_data(run_id, rates, *, versions=None, quarantined=(), cost=100, lat=1000, label="v1"):
    recs = episodes(run_id, rates, cost, lat)
    versions = versions or {sid: 1 for sid in rates}
    report = aggregate_run(run_id, recs, {}, SCNS, seed=1)
    return RunData(
        run_id=run_id,
        suite_id="suite",
        scenario_versions=versions,
        records=recs,
        report=report,
        agent_label=label,
        model="m",
        quarantined=frozenset(quarantined),
    )


ALL_PASS = {sid: [True] for sid in SCNS}


def test_identical_runs_give_no_detectable_change():
    rates = {
        sid: [True, True, False] if i % 2 else [True, True, True] for i, sid in enumerate(SCNS)
    }
    rep = compare_runs(run_data("b", rates), run_data("r", rates), seed=0)
    assert isinstance(rep, CompareReport)
    assert rep.verdict == "no_detectable_change" and rep.delta == 0
    assert rep.detectable_effect_text is None and rep.shared_scenarios == 20


def test_clear_regression_on_five_of_twenty():
    cand = {sid: [i >= 5] for i, sid in enumerate(SCNS)}
    rep = compare_runs(run_data("b", ALL_PASS), run_data("r", cand), seed=0)
    assert rep.verdict == "regression" and rep.ci_high < -rep.margin and rep.delta == -0.25
    failing = [f for f in rep.flips if f.status == "newly_failing"]
    assert len(failing) == 5 and all(f.single_trial for f in failing)


def test_version_mismatch_excluded_with_caution():
    versions = {sid: 1 for sid in SCNS} | {"s03": 2}
    rep = compare_runs(run_data("b", ALL_PASS), run_data("r", ALL_PASS, versions=versions), seed=0)
    assert "version_mismatch:s03" in rep.cautions
    assert rep.shared_scenarios == 19 and "s03" not in {f.scenario_id for f in rep.flips}


def test_quarantined_excluded_and_listed():
    rep = compare_runs(
        run_data("b", ALL_PASS), run_data("r", ALL_PASS, quarantined={"s01"}), seed=0
    )
    assert rep.shared_scenarios == 19 and "quarantined:s01" in rep.cautions


def test_only_in_run_and_baseline():
    base = {k: v for k, v in ALL_PASS.items() if k != "s00"}
    cand = {k: v for k, v in ALL_PASS.items() if k != "s01"}
    rep = compare_runs(run_data("b", base), run_data("r", cand), seed=0)
    assert rep.only_in_run == ["s00"] and rep.only_in_baseline == ["s01"]


def test_flip_classes_need_a_at_least_point_eight_and_b_at_most_point_two():
    base = {"s00": [True] * 5, "s01": [True] * 5, "s02": [True, False] * 3, "s03": [True] * 5}
    cand = {"s00": [False] * 5, "s01": [True, True, True, False, False], "s02": [True, False] * 3,
            "s03": [True] * 5}  # fmt: skip
    rep = compare_runs(run_data("b", base), run_data("r", cand), seed=0)
    status = {f.scenario_id: f.status for f in rep.flips}
    assert status == {"s00": "newly_failing", "s01": "stable", "s02": "flaky", "s03": "stable"}
    nf = next(f for f in rep.flips if f.scenario_id == "s00")
    assert not nf.single_trial and nf.p_value is not None and nf.n_baseline == 5


def test_same_inputs_same_seed_same_output():
    cand = {sid: [i >= 3, True] for i, sid in enumerate(SCNS)}
    base = {sid: [True, i % 2 == 0] for i, sid in enumerate(SCNS)}
    one = compare_runs(run_data("b", base), run_data("r", cand), seed=5).model_dump_json()
    two = compare_runs(run_data("b", base), run_data("r", cand), seed=5).model_dump_json()
    assert one == two


def test_representative_episodes_follow_the_spec():
    base = {"s00": [True, True, True, False, True], "s01": [False] * 5, "s02": [True] * 3}
    cand = {"s00": [False] * 5, "s01": [True] * 5, "s02": [True] * 3}
    rep = compare_runs(run_data("b", base), run_data("r", cand), seed=0)
    by = {f.scenario_id: f for f in rep.flips}
    # newly_failing: the baseline's passing episode, the run's failing one (earliest reps)
    assert (by["s00"].episode_baseline, by["s00"].episode_run) == ("b_s00_0", "r_s00_0")
    assert by["s00"].status == "newly_failing"
    # newly_passing: the reverse
    assert (by["s01"].episode_baseline, by["s01"].episode_run) == ("b_s01_0", "r_s01_0")
    assert by["s01"].status == "newly_passing"
    assert (by["s02"].episode_baseline, by["s02"].episode_run) == ("b_s02_0", "r_s02_0")


def test_cost_latency_and_cautions():
    rep = compare_runs(
        run_data("b", ALL_PASS, cost=100, lat=1000),
        run_data("r", ALL_PASS, cost=150, lat=2000, label="v2"),
        seed=0,
    )
    assert rep.cost.baseline_per_episode_usd_micros == 100 and rep.cost.delta_pct == 50.0
    assert rep.latency.p50_baseline_ms == 1000 and rep.latency.p50_run_ms == 2000
    assert any(c.startswith("agent_versions:") for c in rep.cautions)
    assert rep.params.model_dump() == {"resamples": 2000, "seed": 0}


def test_inconclusive_carries_plain_language_line():
    base = {sid: [True] for sid in list(SCNS)[:6]}
    cand = {sid: [i != 0] for i, sid in enumerate(list(SCNS)[:6])}
    rep = compare_runs(run_data("b", base), run_data("r", cand), seed=0)
    assert rep.verdict == "inconclusive"
    assert rep.detectable_effect_text and "could detect a change" in rep.detectable_effect_text
