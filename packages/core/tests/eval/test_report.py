from check_helpers import scenario
from gauntlet_core.eval import EpisodeRecord, RunReport, aggregate_run, load_rubrics
from gauntlet_core.eval.report import percentile_nearest_rank
from gauntlet_core.schema import NamedCheck, Severity, Verdict
from hypothesis import given
from hypothesis import strategies as st


def rec(i, scn, outcome, cost=100, lat=1000, fid="full", reasons=()):
    return EpisodeRecord(f"ep{i}", scn, 0, outcome, None, cost, lat, fid, tuple(reasons))


SCN = {
    "a": scenario().model_copy(update={"id": "a", "title": "Scenario A"}),
    "b": scenario().model_copy(update={"id": "b", "title": "Scenario B"}),
}


def verdict(crit, result, sev: Severity = "medium", hard=False):
    return Verdict(evaluator="e", criterion=crit, result=result, severity=sev, hard_fail=hard)


def test_excluded_never_enter_rates_and_counts_add_up():
    eps = [
        rec(1, "a", "passed"),
        rec(2, "a", "failed", reasons=["success"]),
        rec(3, "a", "target_error"),
        rec(4, "b", "passed"),
        rec(5, "b", "budget_exhausted"),
        rec(6, "b", "simulator_error"),
    ]
    r = aggregate_run("run", eps, {}, SCN, seed=1)
    assert r.counted == 3 and r.excluded == {
        "target_error": 1,
        "budget_exhausted": 1,
        "simulator_error": 1,
    }
    assert r.counted + sum(r.excluded.values()) == len(eps)
    a, b = r.per_scenario
    assert (a.counted, a.passed, a.rate) == (2, 1, 0.5)
    assert (b.counted, b.passed, b.rate) == (1, 1, 1.0)
    assert r.pass_rate == 0.75 and r.ci_low is not None and r.ci_low <= 0.75 <= (r.ci_high or 0)
    assert a.excluded == {"target_error": 1} and a.episode_ids == ["ep1", "ep2", "ep3"]
    assert a.title == "Scenario A"


def test_seed_stable_output():
    eps = [rec(i, "a" if i % 2 else "b", "passed" if i % 3 else "failed") for i in range(12)]
    one = aggregate_run("r", eps, {}, SCN, seed=7).model_dump_json()
    two = aggregate_run("r", eps, {}, SCN, seed=7).model_dump_json()
    assert one == two
    assert RunReport.model_validate_json(one).run_id == "r"


def test_empty_input_gives_counted_zero():
    r = aggregate_run("r", [], {}, {}, seed=0)
    assert r.counted == 0 and r.pass_rate is None and r.ci_low is None
    assert r.latency_p50_ms is None and r.cost_per_episode_usd_micros == 0 and r.failures == []


def test_scenario_with_only_excluded_has_rate_none_and_left_out_of_mean():
    eps = [rec(1, "a", "target_error"), rec(2, "b", "passed")]
    r = aggregate_run("r", eps, {}, SCN, seed=0)
    a = r.per_scenario[0]
    assert (a.rate, a.ci_low, a.ci_high, a.counted) == (None, None, None, 0)
    assert r.pass_rate == 1.0


def test_latency_percentiles_nearest_rank_on_known_list():
    assert percentile_nearest_rank([10, 20, 30, 40, 50], 0.5) == 30
    assert percentile_nearest_rank([10, 20, 30, 40, 50], 0.95) == 50
    assert percentile_nearest_rank([7], 0.95) == 7
    eps = [rec(i, "a", "passed", lat=100 * (i + 1)) for i in range(10)] + [
        rec(99, "a", "target_error", lat=99999)
    ]
    r = aggregate_run("r", eps, {}, SCN, seed=0)
    assert (r.latency_p50_ms, r.latency_p95_ms) == (500, 1000)


def test_cost_counts_excluded_and_divides_by_all():
    eps = [rec(1, "a", "passed", cost=300), rec(2, "a", "target_error", cost=100)]
    r = aggregate_run("r", eps, {}, SCN, seed=0)
    assert (r.cost_usd_micros, r.cost_per_episode_usd_micros) == (400, 200)


def test_self_preference_flag():
    eps = [rec(1, "a", "passed")]
    same = aggregate_run(
        "r",
        eps,
        {},
        SCN,
        seed=0,
        judge_model="openrouter/qwen/qwen3.7-flash",
        target_model="openrouter/qwen/qwen3.7-max",
    )
    other = aggregate_run(
        "r",
        eps,
        {},
        SCN,
        seed=0,
        judge_model="openrouter/qwen/qwen3.7-flash",
        target_model="openrouter/deepseek/deepseek-v4-flash",
    )
    assert same.caution.self_preference is True and other.caution.self_preference is False


def test_uncalibrated_dimensions_and_hard_fails_and_cautions():
    rubrics = load_rubrics()
    vs = {
        "ep1": [verdict("tone_empathy", "pass", "low"), verdict("groundedness", "fail", "high")],
        "ep2": [
            verdict("tone_empathy", "fail", "low"),
            verdict("groundedness", "na", "high"),
            verdict("task_completion", "error"),
            verdict("policy_adherence", "fail", "high", hard=True),
        ],
    }
    eps = [rec(1, "a", "passed"), rec(2, "a", "failed", reasons=["success"], fid="simulated")]
    r = aggregate_run(
        "r",
        eps,
        vs,
        SCN,
        seed=0,
        rubrics=rubrics,
        target_kind="http",
        unpriced_models=["z/m", "a/b"],
    )
    assert r.caution.uncalibrated_rubrics == [
        "groundedness",
        "policy_adherence",
        "task_completion",
        "tone_empathy",
    ]
    assert r.caution.world_fidelity == "simulated" and r.caution.reduced_coverage is True
    assert r.caution.unpriced_models == ["a/b", "z/m"]
    dims = {d.criterion: d for d in r.dimensions}
    assert dims["tone_empathy"].score == 0.5 and dims["groundedness"].score == 0.0
    assert (dims["groundedness"].na, dims["task_completion"].error) == (1, 1)
    assert dims["task_completion"].score is None and dims["tone_empathy"].gating_allowed is False
    assert r.hard_fail_episodes == ["ep2"]
    assert r.composite_score is not None
    assert (
        aggregate_run(
            "r", eps, vs, SCN, seed=0, target_kind="http", wired=True
        ).caution.reduced_coverage
        is False
    )


def test_failures_ordered_by_deciding_check_severity():
    scn = SCN["a"].model_copy(
        update={
            "forbidden": [
                NamedCheck(
                    id="big_refund",
                    description="d",
                    severity="critical",
                    check={"type": "output", "matcher": {"contains": "x"}},  # type: ignore[arg-type]
                ),
                NamedCheck(
                    id="small",
                    description="d",
                    severity="low",
                    check={"type": "output", "matcher": {"contains": "y"}},  # type: ignore[arg-type]
                ),
            ]
        }
    )
    eps = [
        rec(1, "a", "failed", reasons=["small"]),
        rec(2, "a", "failed", reasons=["big_refund"]),
        rec(3, "a", "failed", reasons=["success"]),
    ]
    r = aggregate_run("r", eps, {}, {"a": scn}, seed=0)
    assert [f.episode_id for f in r.failures] == ["ep2", "ep3", "ep1"]
    assert r.failures[0].reasons == ["big_refund"]


@given(
    st.lists(
        st.tuples(
            st.sampled_from(["a", "b"]),
            st.sampled_from(
                ["passed", "failed", "target_error", "budget_exhausted", "platform_error"]
            ),
        ),
        max_size=30,
    )
)
def test_invariant_counts_add_up(rows):
    eps = [rec(i, s, o) for i, (s, o) in enumerate(rows)]
    r = aggregate_run("r", eps, {}, SCN, seed=3)
    assert r.counted + sum(r.excluded.values()) == len(eps)
    assert sum(s.counted for s in r.per_scenario) == r.counted
    if r.pass_rate is not None:
        assert 0 <= (r.ci_low or 0) <= r.pass_rate <= (r.ci_high or 1) <= 1


@given(st.integers(0, 6), st.integers(0, 6), st.integers(0, 6), st.integers(0, 6))
def test_na_and_error_verdicts_never_change_dimension_score(p, f, na, err):
    base = [verdict("groundedness", "pass")] * p + [verdict("groundedness", "fail")] * f
    noisy = base + [verdict("groundedness", "na")] * na + [verdict("groundedness", "error")] * err
    eps = [rec(1, "a", "passed")]
    a = aggregate_run("r", eps, {"ep1": base}, SCN, seed=0)
    b = aggregate_run("r", eps, {"ep1": noisy}, SCN, seed=0)
    score = lambda r: r.dimensions[0].score if r.dimensions else None  # noqa: E731
    assert score(a) == score(b)
