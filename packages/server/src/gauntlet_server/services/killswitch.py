"""Kill switch (P2-4). State lives in Redis so workers never poll Postgres; the table keeps the
history. Keys: `gauntlet:kill:{workspace}` and `gauntlet:kill:run:{run}`, no TTL until released."""

from __future__ import annotations

from typing import Any

from gauntlet_core.ids import new_id
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from ..db.sec_models import KillSwitch
from ..errors import ApiError
from .audit import audit

__all__ = [
    "KILL_PREFIX",
    "cancel_attack_runs",
    "engage",
    "engaged_keys",
    "killswitch_engaged",
    "release",
]

KILL_PREFIX = "gauntlet:kill:"


def _key(workspace_id: str, run_id: str | None) -> str:
    return f"{KILL_PREFIX}run:{run_id}" if run_id else f"{KILL_PREFIX}{workspace_id}"


async def killswitch_engaged(redis: Any, workspace_id: str, run_id: str | None = None) -> bool:
    if await redis.exists(_key(workspace_id, None)):
        return True
    return bool(run_id and await redis.exists(_key(workspace_id, run_id)))


async def engaged_keys(redis: Any) -> list[str]:
    return [
        k.decode() if isinstance(k, bytes) else k async for k in redis.scan_iter(f"{KILL_PREFIX}*")
    ]


async def engage(
    session: AsyncSession, redis: Any, workspace_id: str, actor: str, *,
    scope: str, run_id: str | None, reason: str,
) -> KillSwitch:  # fmt: skip
    if scope == "run" and not run_id:
        raise ApiError(422, "validation_error", "scope=run needs run_id")
    row = KillSwitch(
        id=new_id("ks"), workspace_id=workspace_id, scope=scope,
        run_id=run_id if scope == "run" else None, engaged_by=actor, reason=reason,
    )  # fmt: skip
    session.add(row)
    await session.flush()
    await audit(
        session, workspace_id, actor, "killswitch.engaged", "killswitch", row.id,
        {"scope": scope, "run_id": row.run_id},
    )  # fmt: skip
    await redis.set(_key(workspace_id, row.run_id), row.id)
    return row


async def release(
    session: AsyncSession, redis: Any, workspace_id: str, actor: str, *,
    scope: str, run_id: str | None,
) -> int:  # fmt: skip
    rid = run_id if scope == "run" else None
    q = update(KillSwitch).where(
        KillSwitch.workspace_id == workspace_id,
        KillSwitch.scope == scope,
        KillSwitch.released_at.is_(None),
    )
    if rid:
        q = q.where(KillSwitch.run_id == rid)
    res = await session.execute(q.values(released_at=func.now()))
    await redis.delete(_key(workspace_id, rid))
    await audit(
        session, workspace_id, actor, "killswitch.released", "killswitch", rid or workspace_id,
        {"scope": scope, "run_id": rid},
    )  # fmt: skip
    return int(res.rowcount)  # type: ignore[attr-defined]


async def active_rows(session: AsyncSession, workspace_id: str) -> list[KillSwitch]:
    q = select(KillSwitch).where(
        KillSwitch.workspace_id == workspace_id, KillSwitch.released_at.is_(None)
    )
    return list((await session.execute(q.order_by(KillSwitch.engaged_at.desc()))).scalars())


async def cancel_attack_runs(session: AsyncSession, workspace_id: str, run_id: str | None) -> int:
    """Cancel queued attack episodes and set the attack runs `cancelled` (outcome stays NULL,
    CQ-S5). Leased episodes are cancelled by the workers that hold them."""
    from sqlalchemy import text

    where = "workspace_id = :w AND attack AND status IN ('queued','running','paused')"
    params: dict[str, Any] = {"w": workspace_id}
    if run_id:
        where += " AND id = :r"
        params["r"] = run_id
    await session.execute(
        text(
            "UPDATE episodes SET status = 'cancelled', finished_at = now() "
            f"WHERE status = 'queued' AND run_id IN (SELECT id FROM runs WHERE {where})"
        ),
        params,
    )
    res = await session.execute(
        text(f"UPDATE runs SET status = 'cancelled', finished_at = now() WHERE {where}"), params
    )
    return int(res.rowcount)  # type: ignore[attr-defined]
