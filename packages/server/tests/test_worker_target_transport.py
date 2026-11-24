"""The worker's target client resolves hostnames and refuses private addresses (SSRF)."""

import httpx
import pytest
from gauntlet_core.targets import TargetError
from gauntlet_server.config import Settings
from gauntlet_server.limits import HostLimiter
from gauntlet_server.worker import target_transport


class Inner(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.seen: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(str(request.url))
        return httpx.Response(200, request=request)


class FakeRedis:
    async def incr(self, key: str) -> int:
        return 1

    async def decr(self, key: str) -> int:
        return 0

    async def expire(self, key: str, s: int) -> None:
        return None

    async def set(self, *a: object, **k: object) -> bool:
        return True


def client(settings: Settings, ips: dict[str, list[str]], inner: Inner) -> httpx.AsyncClient:
    async def resolver(host: str) -> list[str]:
        return ips[host]

    return httpx.AsyncClient(
        transport=target_transport(settings, HostLimiter(FakeRedis()), inner, resolver)
    )


async def test_verified_host_that_resolves_private_is_refused():
    inner = Inner()
    c = client(Settings(env="prod"), {"agent.example.com": ["169.254.169.254"]}, inner)
    with pytest.raises(TargetError):
        await c.post("https://agent.example.com/v1/chat/completions", json={})
    assert inner.seen == []


async def test_literal_private_address_is_refused():
    inner = Inner()
    c = client(Settings(env="prod"), {}, inner)
    with pytest.raises(TargetError):
        await c.get("http://10.0.0.5:8000/")
    assert inner.seen == []


async def test_public_host_and_configured_local_host_pass():
    inner = Inner()
    s = Settings(env="prod", local_target_hosts=frozenset({"dva-sql"}))
    c = client(s, {"agent.example.com": ["93.184.216.34"], "dva-sql": ["172.18.0.5"]}, inner)
    assert (await c.get("https://agent.example.com/x")).status_code == 200
    assert (await c.get("http://dva-sql:8101/x")).status_code == 200
    assert len(inner.seen) == 2
