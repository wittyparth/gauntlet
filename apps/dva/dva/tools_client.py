"""HTTP client for the Gauntlet mock world: `{mock_base}/mock/{token}/tools[/{tool}]`."""

from __future__ import annotations

from typing import Any

import httpx

__all__ = ["ToolsClient"]


class ToolsClient:
    def __init__(self, client: httpx.AsyncClient, mock_base: str, token: str) -> None:
        self._client = client
        self._base = f"{mock_base.rstrip('/')}/mock/{token}/tools"

    async def list_tools(self) -> list[dict[str, Any]]:
        resp = await self._client.get(self._base)
        resp.raise_for_status()
        return resp.json()

    async def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """`{"ok": bool, "result": ..., "error": str | None}`; transport problems become
        `ok: false` so the brain can tell the customer instead of crashing."""
        try:
            resp = await self._client.post(f"{self._base}/{tool}", json=args)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as e:
            return {"ok": False, "result": None, "error": f"tool_transport_error: {e}"}
