"""Guarding tool functions (P4-2)."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from gauntlet_core.ids import new_id

from .errors import NoActiveSession, PolicyBlocked

if TYPE_CHECKING:
    from .guard import Guard
    from .session import Session

__all__ = ["CURRENT", "wrap_tool"]

CURRENT: ContextVar[Session | None] = ContextVar("gauntlet_gateway_session", default=None)


def wrap_tool(
    guard: Guard, fn: Callable[..., Any], tool: str, untrusted_output: bool
) -> Callable[..., Any]:
    sig = inspect.signature(fn)

    @functools.wraps(fn)
    async def guarded(*args: Any, session: Session | None = None, **kwargs: Any) -> Any:
        sess = session or CURRENT.get()
        if sess is None:
            raise NoActiveSession(
                f"{tool}: no gateway session; use `async with session.active()` or session="
            )
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        call_args = dict(bound.arguments)
        call_id = new_id("call")
        decision = await sess.check_tool_call(tool, call_args, call_id=call_id)
        if decision.action == "block":
            if guard.on_block == "raise":
                raise PolicyBlocked(decision)
            return {"error": "blocked_by_policy", "message": decision.message}
        if decision.modified:  # redact: the call goes ahead with the rewritten arguments
            for k, v in (decision.modified.get("args") or {}).items():
                if k in bound.arguments:
                    bound.arguments[k] = v
        try:
            out = fn(*bound.args, **bound.kwargs)
            if inspect.isawaitable(out):
                out = await out
        except Exception as e:
            await sess.record_tool_result(
                call_id, tool, {"error": f"{type(e).__name__}: {e}"}, ok=False,
                untrusted=untrusted_output or None,
            )  # fmt: skip
            raise
        await sess.record_tool_result(call_id, tool, out, untrusted=untrusted_output or None)
        return out

    return guarded
