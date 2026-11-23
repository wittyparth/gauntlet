from __future__ import annotations

from gauntlet_mcp.caps import MARKER, cap


def test_size_cap_with_marker():
    out = cap({"blob": "x" * 50_000})
    assert out.endswith(MARKER) and len(out.encode()) < 20_000 + len(MARKER) + 1
    assert cap({"a": 1}, limit=1000) == '{\n "a": 1\n}'


def test_secret_fields_are_dropped_at_any_depth():
    out = cap({"id": "r", "api_key": "k", "x": [{"Authorization": "b", "ok": 1}]})
    assert "api_key" not in out and "Authorization" not in out and '"ok": 1' in out


async def test_through_the_server(make_client):
    async with make_client() as c:
        big = (await c.call_tool("get_run_report", {"run_id": "run_big"})).content[0].text
        ok = (await c.call_tool("get_run_report", {"run_id": "run_1"})).content[0].text
    assert big.endswith(MARKER)
    assert "gk_leak" not in ok and "secret_token" not in ok
