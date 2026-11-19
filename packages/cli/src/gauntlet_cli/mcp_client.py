"""Read-only MCP client for the scanner: `initialize`, `tools/list`, `resources/list` and
`prompts/list`. It never sends `tools/call` (or any other request).

Only connect to servers you are allowed to connect to. `--stdio` launches the given command with
a minimal environment (PATH plus explicit values) and terminates it afterwards.
"""

from __future__ import annotations

import os
from contextlib import AsyncExitStack
from typing import Any

import anyio
from gauntlet_core.security.scan import TransportInfo
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import (
    create_mcp_http_client,  # pyright: ignore[reportPrivateImportUsage]
    streamable_http_client,
)

__all__ = ["ConnectError", "fetch_listing"]


class ConnectError(Exception):
    """The server could not be reached or did not complete the handshake."""


async def _listing(session: ClientSession) -> dict[str, Any]:
    await session.initialize()
    listing: dict[str, Any] = {}
    tools = await session.list_tools()
    listing["tools"] = [t.model_dump(mode="json", by_alias=True) for t in tools.tools]
    for key, call in (("resources", session.list_resources), ("prompts", session.list_prompts)):
        try:
            res = await call()
        except Exception:  # the server need not implement them
            continue
        listing[key] = [r.model_dump(mode="json", by_alias=True) for r in getattr(res, key)]
    return listing


async def fetch_listing(
    *,
    stdio: list[str] | None = None,
    url: str | None = None,
    headers: dict[str, str] | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> tuple[dict[str, Any], TransportInfo]:
    try:
        with anyio.fail_after(timeout):
            async with AsyncExitStack() as stack:
                if stdio:
                    params = StdioServerParameters(
                        command=stdio[0],
                        args=stdio[1:],
                        env={"PATH": os.environ.get("PATH", ""), **(env or {})},
                    )
                    r, w = await stack.enter_async_context(stdio_client(params))
                    info = TransportInfo(kind="stdio")
                else:
                    assert url is not None
                    client = create_mcp_http_client(headers=headers) if headers else None
                    r, w = await stack.enter_async_context(
                        streamable_http_client(url, http_client=client)
                    )
                    creds = any(k.lower() == "authorization" for k in (headers or {}))
                    info = TransportInfo(
                        kind="http",
                        url=url,
                        has_credentials=creds,
                        connected_without_auth=not creds,
                    )
                session = await stack.enter_async_context(ClientSession(r, w))
                return await _listing(session), info
    except TimeoutError as e:
        raise ConnectError(f"timed out after {timeout:g}s") from e
    except BaseException as e:  # connection, protocol and process errors (incl. task groups)
        if isinstance(e, KeyboardInterrupt | SystemExit):
            raise
        raise ConnectError(f"{type(e).__name__}: {e}") from e
