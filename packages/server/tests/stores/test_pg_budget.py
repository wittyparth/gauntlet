from __future__ import annotations

import asyncio

import pytest
from gauntlet_server.db import Sessionmaker
from gauntlet_server.stores import PgBudgetLedger
from pg_helpers import add_run, one
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration


async def totals(sm: Sessionmaker) -> tuple[int, int]:
    row = await one(sm, "SELECT reserved_usd_micros, spent_usd_micros FROM runs WHERE id='run_1'")
    return row[0], row[1]


async def test_reserve_within_and_over_budget(sm: Sessionmaker):
    await add_run(sm, budget=1000)
    ledger = PgBudgetLedger(sm)
    assert await ledger.reserve("run_1", 600) is True
    assert await ledger.reserve("run_1", 400) is True  # exactly the budget
    assert await ledger.reserve("run_1", 1) is False
    assert await totals(sm) == (1000, 0)
    assert await ledger.reserve("missing_run", 1) is False


async def test_fifty_concurrent_reservations_never_exceed_the_budget(sm: Sessionmaker):
    await add_run(sm, budget=1000)
    ledger = PgBudgetLedger(sm)
    results = await asyncio.gather(*(ledger.reserve("run_1", 100) for _ in range(50)))
    assert sum(results) == 10
    assert await totals(sm) == (1000, 0)


async def test_settle_moves_reserved_to_spent(sm: Sessionmaker):
    await add_run(sm, budget=1000)
    ledger = PgBudgetLedger(sm)
    assert await ledger.reserve("run_1", 300)
    await ledger.settle("run_1", 300, 120)
    assert await totals(sm) == (0, 120)
    assert await ledger.reserve("run_1", 880) and not await ledger.reserve("run_1", 1)


async def test_settle_may_exceed_the_reservation_but_counters_never_go_negative(sm: Sessionmaker):
    await add_run(sm, budget=1000)
    ledger = PgBudgetLedger(sm)
    assert await ledger.reserve("run_1", 100)
    await ledger.settle("run_1", 100, 150)  # estimates are estimates
    assert await totals(sm) == (0, 150)
    with pytest.raises(IntegrityError):
        await ledger.settle("run_1", 10, 0)  # nothing is reserved any more
    assert await totals(sm) == (0, 150)


async def test_concurrent_reserve_and_settle_stay_consistent(sm: Sessionmaker):
    await add_run(sm, budget=1000)
    ledger = PgBudgetLedger(sm)

    async def worker() -> None:
        for _ in range(5):
            if await ledger.reserve("run_1", 50):
                await ledger.settle("run_1", 50, 30)

    await asyncio.gather(*(worker() for _ in range(10)))
    reserved, spent = await totals(sm)
    assert reserved == 0 and spent % 30 == 0 and spent <= 1000


async def test_completing_a_run_reconciles_the_ledger_with_the_journal(sm: Sessionmaker):
    """A worker killed between recording an effect and settling it leaves the run with a
    reservation nobody will release and spend lower than the effect costs (found by the chaos
    test). When the run completes, `reserved` is zero and `spent` equals the episode costs."""
    from gauntlet_server.services.runs import maybe_complete_run
    from pg_helpers import add_episode

    await add_run(sm, budget=10_000, status="running")
    await add_episode(sm, "ep_a", status="done", cost_usd_micros=700)
    await add_episode(sm, "ep_b", status="done", cost_usd_micros=300)
    ledger = PgBudgetLedger(sm)
    assert await ledger.reserve("run_1", 500)  # the killed worker's reservation
    await ledger.settle("run_1", 0, 600)  # and spend that lags the journal (600 < 1000)
    async with sm() as s, s.begin():
        assert await maybe_complete_run(s, "run_1")
    assert await totals(sm) == (0, 1000)
