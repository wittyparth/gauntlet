from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from gauntlet_server.services.production import sweep_retention
from ingest_helpers import fixture, post
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def counts(sm) -> list[int]:
    out = []
    async with sm() as s:
        for t in ("prod_conversations", "prod_events", "prod_spans_seen"):
            out.append((await s.execute(text(f"SELECT count(*) FROM {t}"))).scalar())
    return out


async def test_sweep_deletes_only_expired_rows_and_their_children(client, state, sm):
    await post(client, fixture("openinference_support"))  # event times are in 2026
    await post(client, fixture("genai_support"))
    assert await counts(sm) == [2, 11, 9]
    soon = datetime.fromtimestamp(1_780_000_000, tz=UTC) + timedelta(days=1)
    assert await sweep_retention(state, now=soon) == {"conversations": 0, "span_markers": 0}
    assert await counts(sm) == [2, 11, 9]
    async with sm() as s, s.begin():  # make one conversation and its markers old
        await s.execute(
            text(
                "UPDATE prod_conversations SET ended_at = CASE external_session_id "
                "WHEN 'sess-2' THEN now() - interval '90 days' ELSE now() END"
            )
        )
        await s.execute(
            text(
                "UPDATE prod_spans_seen SET created_at = now() - interval '90 days' "
                "WHERE trace_id = :t"
            ),
            {"t": "b" * 32},
        )
    res = await sweep_retention(state, batch=1)
    assert res == {"conversations": 1, "span_markers": 3}
    async with sm() as s:
        left = (
            (await s.execute(text("SELECT external_session_id FROM prod_conversations")))
            .scalars()
            .all()
        )
    assert left == ["sess-1"] and await counts(sm) == [1, 7, 6]
