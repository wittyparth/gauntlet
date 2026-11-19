import httpx
from gauntlet_server.app import app


async def test_healthz_returns_ok():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and isinstance(body["version"], str)
