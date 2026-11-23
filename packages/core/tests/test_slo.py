from datetime import UTC, datetime, timedelta

import pytest
from gauntlet_core.slo import MAX_BURN, Sample, burn_alerts, slo_status

NOW = datetime(2026, 6, 1, 12, tzinfo=UTC)
DAY = timedelta(days=1)


def spread(good: int, bad: int, within: timedelta = timedelta(hours=1)) -> list[Sample]:
    n = good + bad
    out = []
    for i in range(n):
        ts = NOW - within * (i / max(n, 1))
        out.append(Sample(ts, i >= bad))
    return out


def test_empty_window_is_unknown():
    st = slo_status([], 0.9, DAY, NOW)
    assert st.state == "unknown" and st.compliance is None and not st.breached
    old = [Sample(NOW - 10 * DAY, True)]
    assert slo_status(old, 0.9, DAY, NOW).state == "unknown"


@pytest.mark.parametrize(
    ("good", "bad", "objective", "budget"),
    [(100, 0, 0.9, 1.0), (95, 5, 0.9, 0.5), (90, 10, 0.9, 0.0), (80, 20, 0.9, -1.0)],
)
def test_error_budget_table(good, bad, objective, budget):
    st = slo_status(spread(good, bad), objective, DAY, NOW)
    assert st.error_budget_remaining == pytest.approx(budget)


def test_breach_needs_the_interval_to_exclude_the_objective():
    # 8/10 good vs objective 0.9: point estimate below, interval still contains 0.9
    small = slo_status(spread(8, 2), 0.9, DAY, NOW)
    assert small.compliance == 0.8 and small.warning and not small.breached
    # 800/1000 good: interval excludes 0.9
    big = slo_status(spread(800, 200), 0.9, DAY, NOW)
    assert big.breached and big.state == "breached"
    ok = slo_status(spread(95, 5), 0.9, DAY, NOW)
    assert ok.state == "ok"


def test_burn_rates_by_window():
    samples = [Sample(NOW - timedelta(minutes=10), False)] * 5 + [
        Sample(NOW - timedelta(days=2), True)
    ] * 95
    st = slo_status(samples, 0.99, 7 * DAY, NOW)
    assert st.burn_rates["1h"] == pytest.approx(100.0)  # all bad in the last hour
    assert st.burn_rates["3d"] == pytest.approx(5 / 100 / 0.01)
    assert "6h" in st.burn_rates


def test_burn_alert_pairs():
    hot = slo_status(spread(0, 50), 0.99, DAY, NOW)
    assert burn_alerts(hot) == ["fast", "slow"]
    calm = slo_status(spread(100, 0), 0.99, DAY, NOW)
    assert burn_alerts(calm) == []


def test_zero_allowed_bad_events():
    st = slo_status(spread(9, 1), 1.0, DAY, NOW)
    assert st.burn_rates["1h"] == MAX_BURN and st.error_budget_remaining == 0.0


def test_bad_objective_rejected():
    with pytest.raises(ValueError):
        slo_status([], 0.0, DAY, NOW)
