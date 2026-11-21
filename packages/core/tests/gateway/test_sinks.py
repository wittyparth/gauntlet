# pyright: reportOptionalMemberAccess=false
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import httpx
from gauntlet_core.gateway import DecisionRecord, HttpSink, JsonlSink, MemorySink


def rec(i: int = 0) -> DecisionRecord:
    return DecisionRecord(
        id=f"gdc_{i}",
        ts=datetime(2026, 1, 1, tzinfo=UTC),
        session_id="s",
        policy_id="p",
        policy_version=1,
        mode="enforce",
        kind="tool_call",
        tool="t",
        action="allow",
        enforced=True,
    )


async def wait_for(cond, timeout=3.0):
    for _ in range(int(timeout / 0.005)):
        if cond():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition not reached")


def server(statuses=None):
    batches: list[list[dict]] = []
    codes = list(statuses or [])

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/gateway/decisions"
        assert request.headers["authorization"] == "Bearer key"
        code = codes.pop(0) if codes else 200
        if code < 400:
            batches.append(json.loads(request.content)["records"])
        return httpx.Response(code, json={"accepted": 0})

    return httpx.MockTransport(handler), batches


async def test_memory_and_jsonl_sinks(tmp_path):
    m = MemorySink()
    await m.write(rec(1))
    assert m.records[0].id == "gdc_1"
    j = JsonlSink(tmp_path / "d.jsonl")
    await asyncio.gather(*(j.write(rec(i)) for i in range(20)))
    lines = (tmp_path / "d.jsonl").read_text().splitlines()
    assert len(lines) == 20 and {json.loads(x)["id"] for x in lines} == {
        f"gdc_{i}" for i in range(20)
    }
    assert json.loads(lines[0])["action"] == "allow"


async def test_batches_flush_at_threshold_and_never_exceed_the_batch_size():
    transport, batches = server()
    sink = HttpSink("http://api.test", "key", flush_interval_s=60, transport=transport,
                    flush_threshold=200, batch_size=50)  # fmt: skip
    for i in range(210):
        await sink.write(rec(i))
    await wait_for(lambda: sink.sent >= 200)
    assert all(len(b) <= 50 for b in batches)
    await sink.aclose()  # flushes the remainder
    assert sink.sent == 210 and sum(len(b) for b in batches) == 210
    assert [r["id"] for b in batches for r in b] == [f"gdc_{i}" for i in range(210)]


async def test_interval_flush_without_threshold():
    transport, _ = server()
    sink = HttpSink("http://api.test", "key", flush_interval_s=0.01, transport=transport)
    await sink.write(rec())
    await wait_for(lambda: sink.sent == 1)
    await sink.aclose()


async def test_backoff_doubles_to_the_cap_then_recovers():
    transport, _ = server([503, 503, 503, 503, 503, 503])
    delays: list[float] = []

    async def fake_sleep(d: float) -> None:
        delays.append(d)
        await asyncio.sleep(0)

    sink = HttpSink("http://api.test", "key", flush_interval_s=0.001, max_backoff_s=8,
                    transport=transport, sleep=fake_sleep)  # fmt: skip
    await sink.write(rec())
    await wait_for(lambda: sink.sent == 1)
    assert delays[:5] == [1.0, 2.0, 4.0, 8.0, 8.0]  # exponential, capped
    assert sink.failures >= 6 and sink.queued == 0
    await sink.aclose()


async def test_connection_errors_are_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json={})

    async def fast(d):
        await asyncio.sleep(0)

    sink = HttpSink("http://api.test", "key", flush_interval_s=0.001,
                    transport=httpx.MockTransport(handler), sleep=fast)  # fmt: skip
    await sink.write(rec())
    await wait_for(lambda: sink.sent == 1)
    await sink.aclose()


async def test_drop_oldest_is_counted():
    transport, _ = server([503] * 100)

    async def hold(d):
        await asyncio.sleep(10)

    sink = HttpSink("http://api.test", "key", max_queue=5, flush_interval_s=60,
                    flush_threshold=10_000, transport=transport, sleep=hold)  # fmt: skip
    for i in range(12):
        await sink.write(rec(i))
    assert sink.queued == 5 and sink.dropped == 7
    assert [r.id for r in sink._queue] == [f"gdc_{i}" for i in range(7, 12)]
    sink._closed = True
    sink._task.cancel()
    await sink._client.aclose()


async def test_rejected_batch_is_dropped_not_retried_forever():
    transport, _ = server([400])
    sink = HttpSink("http://api.test", "key", flush_interval_s=0.001, transport=transport)
    await sink.write(rec())
    await wait_for(lambda: sink.dropped == 1)
    assert sink.queued == 0 and sink.sent == 0
    await sink.aclose()


async def test_write_never_blocks_on_a_dead_server():
    def handler(request):
        raise httpx.ConnectError("down")

    async def hold(d):
        await asyncio.sleep(10)

    sink = HttpSink("http://api.test", "key", flush_interval_s=60,
                    transport=httpx.MockTransport(handler), sleep=hold)  # fmt: skip
    await asyncio.wait_for(asyncio.gather(*(sink.write(rec(i)) for i in range(100))), 1.0)
    sink._closed = True
    sink._task.cancel()
    await sink._client.aclose()
