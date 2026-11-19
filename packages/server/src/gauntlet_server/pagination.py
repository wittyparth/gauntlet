"""Opaque keyset cursors: base64 of the last (created_at, id); lists are newest first."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .errors import ApiError

__all__ = ["Page", "decode_cursor", "encode_cursor", "paginate"]

MAX_LIMIT = 200


def encode_cursor(created_at: datetime, id: str) -> str:
    raw = json.dumps([created_at.isoformat(), id]).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        ts, id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(ts), str(id)
    except (ValueError, TypeError) as e:
        raise ApiError(422, "validation_error", "invalid cursor") from e


class Page:
    def __init__(self, limit: int = 50, cursor: str | None = None) -> None:
        self.limit = max(1, min(limit, MAX_LIMIT))
        self.cursor = decode_cursor(cursor) if cursor else None


async def paginate(
    session: AsyncSession,
    query: Select[Any],
    model: Any,
    page: Page,
    render: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    """Keyset pagination on (created_at, id) over `query`, newest first."""
    if page.cursor:
        ts, id = page.cursor
        query = query.where(or_(model.created_at < ts, and_(model.created_at == ts, model.id < id)))
    query = query.order_by(model.created_at.desc(), model.id.desc()).limit(page.limit + 1)
    rows = list((await session.execute(query)).scalars())
    more = len(rows) > page.limit
    rows = rows[: page.limit]
    nxt = encode_cursor(rows[-1].created_at, rows[-1].id) if more and rows else None
    return {"items": [render(r) for r in rows], "next_cursor": nxt}
