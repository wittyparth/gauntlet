from __future__ import annotations

import httpx
import respx
from dva.app import create_app
from dva.config import Settings

MOCK = "http://mock.test"


def client(flaws: set[str] | None = None, brain: str = "scripted") -> httpx.AsyncClient:
    app = create_app(lambda: flaws or set(), Settings(brain=brain, mock_base=MOCK))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://dva")


async def test_400_without_episode_header():
    async with client() as c:
        r = await c.post(
            "/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]}
        )
    assert r.status_code == 400 and "X-Gauntlet-Episode" in r.json()["error"]


async def test_400_on_bad_body():
    async with client() as c:
        r = await c.post("/v1/chat/completions", json={}, headers={"X-Gauntlet-Episode": "t"})
    assert r.status_code == 400


async def test_reply_shape_is_openai_compatible_and_healthz():
    async with client() as c:
        r = await c.post(
            "/v1/chat/completions",
            json={"model": "dva", "messages": [{"role": "user", "content": "hello"}]},
            headers={"X-Gauntlet-Episode": "tok"},
        )
        h = await c.get("/healthz")
    body = r.json()
    assert r.status_code == 200 and body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert isinstance(body["choices"][0]["message"]["content"], str)
    assert body["choices"][0]["finish_reason"] == "stop"
    assert h.json()["ok"] is True


@respx.mock(assert_all_called=False)
async def test_tool_calls_hit_the_mock_base_with_the_token_path(respx_mock):
    respx_mock.route(host="dva").pass_through()
    route = respx_mock.post(f"{MOCK}/mock/tok_1/tools/lookup_order").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "id": "ord_1",
                    "status": "shipped",
                    "tracking": {"eta": "2026-03-18"},
                    "delivered_at": None,
                },
                "error": None,
            },
        )
    )
    async with client() as c:
        r = await c.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "where is ord_1?"}]},
            headers={"X-Gauntlet-Episode": "tok_1"},
        )
    assert route.called and route.calls[0].request.content == b'{"order_id":"ord_1"}'
    assert "shipped" in r.json()["choices"][0]["message"]["content"]


@respx.mock(assert_all_called=False)
async def test_mock_base_header_overrides_the_setting(respx_mock):
    respx_mock.route(host="dva").pass_through()
    route = respx_mock.post("http://other.test/mock/tok/tools/lookup_order").mock(
        return_value=httpx.Response(200, json={"ok": False, "result": None, "error": "not_found"})
    )
    async with client() as c:
        await c.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "where is ord_9?"}]},
            headers={"X-Gauntlet-Episode": "tok", "X-Gauntlet-Mock-Base": "http://other.test"},
        )
    assert route.called


@respx.mock(assert_all_called=False)
async def test_tool_transport_failure_becomes_a_reply_not_a_crash(respx_mock):
    respx_mock.route(host="dva").pass_through()
    respx_mock.post(f"{MOCK}/mock/tok/tools/lookup_order").mock(return_value=httpx.Response(500))
    async with client() as c:
        r = await c.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "where is ord_1?"}]},
            headers={"X-Gauntlet-Episode": "tok"},
        )
    assert r.status_code == 200
