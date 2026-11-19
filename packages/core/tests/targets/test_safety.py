import httpx
import pytest
from gauntlet_core.targets import GuardedTransport, TargetError, UrlPolicy, check_url

STRICT = UrlPolicy(allow_private=False, local_hosts=frozenset({"agent.internal"}))


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/",
        "http://192.168.1.2/",
        "http://[::1]/",
        "http://[fd00::1]/",
        "file:///etc/passwd",
        "ftp://example.com/",
        "http://user:pw@example.com/",
    ],
)
def test_blocked(url):
    with pytest.raises(TargetError) as e:
        check_url(url, STRICT)
    assert e.value.code == "blocked_url"


def test_allowed():
    check_url("https://8.8.8.8/x", STRICT)
    check_url("http://agent.internal:8080/x", STRICT)
    check_url("http://127.0.0.1:9/", UrlPolicy(allow_private=True))
    check_url("https://api.example.com/", STRICT)  # a name: resolved at connect time


async def test_dns_rebinding_blocked_by_transport():
    answers = [["93.184.216.34"], ["10.0.0.7"]]

    async def resolver(host: str) -> list[str]:
        return answers.pop(0)

    reached: list[str] = []

    class Inner(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            reached.append(str(request.url))
            return httpx.Response(200, json={})

    t = GuardedTransport(Inner(), STRICT, resolver)
    async with httpx.AsyncClient(transport=t) as c:
        assert (await c.get("http://rebind.example.com/")).status_code == 200  # public at first
        with pytest.raises(TargetError):
            await c.get("http://rebind.example.com/")  # now private
    assert len(reached) == 1
