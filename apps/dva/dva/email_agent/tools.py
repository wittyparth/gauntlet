"""Small helpers over the mock mailbox tools. `send_email` only records into the mock world."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

__all__ = ["Call", "read_email", "send_email"]

Call = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


async def read_email(call: Call, email_id: str) -> dict[str, Any]:
    return await call("read_email", {"email_id": email_id})


async def send_email(call: Call, to: str, subject: str, body: str) -> dict[str, Any]:
    return await call("send_email", {"to": to, "subject": subject, "body": body})
