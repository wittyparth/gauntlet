from __future__ import annotations

import httpx
import respx
from cli_helpers import invoke


@respx.mock
def test_seed_prints_ids_and_sends_key(runner):
    route = respx.post("http://api.test/v1/dev/seed").mock(
        return_value=httpx.Response(200, json={"project_id": "prj_1", "suite_ids": ["suite_1"]})
    )
    res = invoke(runner, ["demo", "seed", "--api-url", "http://api.test", "--api-key", "k1"])
    assert res.exit_code == 0 and "prj_1" in res.stdout
    req = route.calls[0].request
    assert req.headers["authorization"] == "Bearer k1"
    assert b'"reset":false' in req.content.replace(b" ", b"")


@respx.mock
def test_seed_reset_flag(runner):
    route = respx.post("http://api.test/v1/dev/seed").mock(
        return_value=httpx.Response(200, json={})
    )
    invoke(runner, ["demo", "seed", "--api-url", "http://api.test", "--reset"])
    assert b"true" in route.calls[0].request.content


@respx.mock
def test_non_dev_server_gives_clear_error(runner):
    respx.post("http://api.test/v1/dev/seed").mock(return_value=httpx.Response(404))
    res = invoke(runner, ["demo", "seed", "--api-url", "http://api.test"])
    assert res.exit_code == 3 and "GAUNTLET_ENV=dev" in res.stderr


@respx.mock
def test_unreachable_server(runner):
    respx.post("http://api.test/v1/dev/seed").mock(side_effect=httpx.ConnectError("refused"))
    res = invoke(runner, ["demo", "seed", "--api-url", "http://api.test"])
    assert res.exit_code == 3 and "cannot reach" in res.stderr
