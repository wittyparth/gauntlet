"""On the HTTP transport the caller's own bearer key is required; the server's key is never lent."""

from types import SimpleNamespace
from typing import Any

import pytest
from gauntlet_mcp.client import ApiError, Client
from gauntlet_mcp.server import _client_for


def ctx(authorization: str | None) -> Any:
    return SimpleNamespace(headers={"authorization": authorization} if authorization else {})


def test_http_without_a_header_is_refused():
    base = Client("http://api.test", "gk_server_key")
    with pytest.raises(ApiError) as e:
        _client_for(base, ctx(None), require_header=True)
    assert e.value.status == 401


def test_http_uses_the_callers_key():
    base = Client("http://api.test", "gk_server_key")
    got = _client_for(base, ctx("Bearer gk_caller"), require_header=True)
    assert got.api_key == "gk_caller"


def test_stdio_falls_back_to_the_env_key():
    base = Client("http://api.test", "gk_server_key")
    assert _client_for(base, ctx(None)).api_key == "gk_server_key"
