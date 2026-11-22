from __future__ import annotations

import re

import pytest
from ingest_helpers import SECRETS, fixture, post
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def dump_all_tables(sm) -> str:
    out: list[str] = []
    async with sm() as s:
        tables = (
            (await s.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")))
            .scalars()
            .all()
        )
        for t in tables:
            q = text(f'SELECT row_to_json(x)::text FROM "{t}" x')
            out.extend((await s.execute(q)).scalars().all())
    return "\n".join(out)


async def test_planted_pii_is_nowhere_after_ingest(client, sm):
    r = await post(client, fixture("planted_pii"))
    assert r.status_code == 200
    (c,) = (await client.get("/v1/production/conversations")).json()["items"]
    detail = (await client.get(f"/v1/production/conversations/{c['id']}")).text
    listing = (await client.get("/v1/production/conversations")).text
    stats = (await client.get("/v1/production/stats")).text
    search = (await client.get("/v1/production/conversations", params={"q": "example"})).text
    blob = await dump_all_tables(sm) + detail + listing + stats + search
    for secret in SECRETS:
        assert secret not in blob, secret
    assert "Bearer AKIA" not in blob and '"authorization"' not in detail
    red = c["redaction"]
    assert red["email"] >= 3 and red["secret"] >= 1 and red["card"] >= 1
    assert "[EMAIL_" in detail and "[CARD_" in detail


async def test_q_cannot_find_the_raw_value(client):
    await post(client, fixture("planted_pii"))
    raw = await client.get("/v1/production/conversations", params={"q": "jane.doe"})
    assert raw.json()["items"] == []
    token = await client.get("/v1/production/conversations", params={"q": "[EMAIL_"})
    assert len(token.json()["items"]) == 1


async def test_same_email_same_token_across_batches(client):
    spans = fixture("planted_pii")["resourceSpans"][0]["scopeSpans"][0]["spans"]

    def wrap(sp):
        return {"resourceSpans": [{"scopeSpans": [{"spans": sp}]}]}

    await post(client, wrap(spans[:1]))
    await post(client, wrap(spans[1:]))
    (c,) = (await client.get("/v1/production/conversations")).json()["items"]
    detail = (await client.get(f"/v1/production/conversations/{c['id']}")).json()
    tokens = set(re.findall(r"\[EMAIL_[0-9a-f]{6}\]", str(detail["events"])))
    assert len(tokens) == 1  # one address everywhere, the same token in both batches
