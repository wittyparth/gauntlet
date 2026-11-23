"""Typed-enough async REST client: the caller's key and nothing else."""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_URL = "http://localhost:8000"


class ApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"API answered {status}: {detail}")
        self.status = status


class Client:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base = (base_url or os.environ.get("GAUNTLET_API_URL") or DEFAULT_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("GAUNTLET_API_KEY", "")
        self._transport = transport

    def with_key(self, api_key: str | None) -> Client:
        """A client acting as another caller (key from the MCP request header)."""
        return Client(self.base, api_key or self.api_key, self._transport)

    async def request(self, method: str, path: str, **kw: Any) -> Any:
        if not self.api_key:
            raise ApiError(401, "no API key: set GAUNTLET_API_KEY or send an Authorization header")
        async with httpx.AsyncClient(transport=self._transport, timeout=30.0) as http:
            try:
                resp = await http.request(
                    method,
                    self.base + path,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    **kw,
                )
            except httpx.HTTPError as e:
                raise ApiError(0, f"cannot reach {self.base}: {type(e).__name__}") from e
        if resp.status_code >= 400:
            try:
                body = resp.json()
                detail = body.get("error", {}).get("message") or body.get("detail") or resp.text
            except ValueError:
                detail = resp.text
            raise ApiError(resp.status_code, str(detail)[:300])
        return resp.json()

    async def get(self, path: str, **params: Any) -> Any:
        return await self.request("GET", path, params={k: v for k, v in params.items() if v})

    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return await self.request("POST", path, json=body or {})
