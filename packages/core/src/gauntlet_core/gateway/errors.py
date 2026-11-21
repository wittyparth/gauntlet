"""Gateway exceptions."""

from __future__ import annotations

from gauntlet_core.policy import GatewayDecision

__all__ = ["ApprovalExpired", "NoActiveSession", "PolicyBlocked"]


class PolicyBlocked(Exception):
    """A guarded call was stopped by policy. `decision` says which rule and why."""

    def __init__(self, decision: GatewayDecision) -> None:
        super().__init__(decision.message or f"blocked by policy rule {decision.rule_id}")
        self.decision = decision


class ApprovalExpired(Exception):
    """The approval service reported the request expired before anyone decided."""


class NoActiveSession(RuntimeError):
    """A wrapped tool ran outside `async with session.active()` and without `session=`."""
