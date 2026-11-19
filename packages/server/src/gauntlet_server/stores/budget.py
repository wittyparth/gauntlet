"""Postgres budget ledger (hard-cores 1.5). The conditional UPDATE is the whole algorithm:
Postgres re-evaluates its WHERE after waiting on the row lock, so concurrent reservations
can never push spent + reserved over the budget."""

from __future__ import annotations

from sqlalchemy import text

from gauntlet_server.db import Sessionmaker

__all__ = ["PgBudgetLedger"]


class PgBudgetLedger:
    def __init__(self, sessionmaker: Sessionmaker) -> None:
        self._sm = sessionmaker

    async def reserve(self, run_id: str, usd_micros: int) -> bool:
        async with self._sm() as s, s.begin():
            res = await s.execute(
                text(
                    "UPDATE runs SET reserved_usd_micros = reserved_usd_micros + :x "
                    "WHERE id = :run AND spent_usd_micros + reserved_usd_micros + :x "
                    "<= budget_usd_micros"
                ),
                {"run": run_id, "x": usd_micros},
            )
            return res.rowcount == 1  # type: ignore[attr-defined]

    async def settle(self, run_id: str, reserved: int, actual: int) -> None:
        async with self._sm() as s, s.begin():
            await s.execute(
                text(
                    "UPDATE runs SET reserved_usd_micros = reserved_usd_micros - :reserved, "
                    "spent_usd_micros = spent_usd_micros + :actual WHERE id = :run"
                ),
                {"run": run_id, "reserved": reserved, "actual": actual},
            )
