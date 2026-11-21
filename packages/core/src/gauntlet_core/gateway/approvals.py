"""Human approval for `require_approval` decisions (P4-2)."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Literal, Protocol

import httpx

from gauntlet_core.policy import GatewayDecision

from .decision import DecisionRecord
from .errors import ApprovalExpired

__all__ = ["ApprovalHandler", "CallbackApprovals", "HttpApprovals"]

Outcome = Literal["approved", "denied"]


class ApprovalHandler(Protocol):
    async def request(self, decision: GatewayDecision, record: DecisionRecord) -> Outcome: ...


Callback = Callable[[GatewayDecision, DecisionRecord], Outcome | bool | Awaitable[Outcome | bool]]


class CallbackApprovals:
    """Decide in-process: `fn(decision, record)` returns "approved"/"denied" or a bool,
    synchronously or as an awaitable."""

    def __init__(self, fn: Callback) -> None:
        self.fn = fn

    async def request(self, decision: GatewayDecision, record: DecisionRecord) -> Outcome:
        res = self.fn(decision, record)
        if inspect.isawaitable(res):
            res = await res
        if res is True or res == "approved":
            return "approved"
        return "denied"


class HttpApprovals:
    """Create the approval on the server (with the exact action) and poll until a person
    decides. `expires_in_s` should match the guard's `approval_timeout_s`. An expired request
    raises `ApprovalExpired`; transport errors propagate (the guard treats both as a timeout)."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        poll_interval_s: float = 1.0,
        *,
        expires_in_s: float = 300.0,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.poll_interval_s = poll_interval_s
        self.expires_in_s = expires_in_s
        self._client = client or httpx.AsyncClient(
            base_url=api_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=10.0,
        )

    async def request(self, decision: GatewayDecision, record: DecisionRecord) -> Outcome:
        body = {
            "id": record.approval.id if record.approval else None,
            "record": record.model_dump(mode="json"),
            "expires_in_s": int(self.expires_in_s),
        }
        r = await self._client.post("/v1/gateway/approvals", json=body)
        r.raise_for_status()
        approval_id = r.json()["id"]
        while True:
            r = await self._client.get(f"/v1/gateway/approvals/{approval_id}")
            r.raise_for_status()
            status = r.json()["status"]
            if status == "approved":
                return "approved"
            if status == "denied":
                return "denied"
            if status == "expired":
                raise ApprovalExpired(approval_id)
            await asyncio.sleep(self.poll_interval_s)

    async def aclose(self) -> None:
        await self._client.aclose()
