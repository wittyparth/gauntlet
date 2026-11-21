"""One conversation as the gateway sees it (P4-2): the event prefix, the decisions, the
approval flow. Everything the agent could be harmed by (sink, approvals, engine bugs) is
contained here: only a policy decision ever reaches the agent."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from time import perf_counter_ns
from typing import TYPE_CHECKING, Literal, cast

from gauntlet_core.checks import PrefixView, ProposedAction
from gauntlet_core.ids import new_id
from gauntlet_core.policy import GatewayDecision
from gauntlet_core.schema import Event, Json, Origin

from .decision import ApprovalInfo, DecisionRecord, render_args, render_evidence
from .errors import ApprovalExpired

if TYPE_CHECKING:
    from .guard import Guard

__all__ = ["MAX_PREFIX", "Session"]

log = logging.getLogger("gauntlet.gateway")

MAX_PREFIX = 500


class Session:
    def __init__(self, guard: Guard, session_id: str, user_id: str | None = None) -> None:
        self.guard = guard
        self.session_id = session_id
        self.user_id = user_id  # caller-supplied, untrusted (CQ-G8)
        self._events: list[Event] = []
        self._seq = 0
        self._lock = asyncio.Lock()

    @property
    def events(self) -> list[Event]:
        return list(self._events)

    # -- recording --------------------------------------------------------------------------

    def _append(
        self,
        kind: Literal["user_message", "agent_message", "tool_call", "tool_result"],
        actor: Literal["user", "agent", "tool"],
        payload: Json,
        origin: Origin | None = None,
    ) -> Event:
        self._seq += 1
        ev = Event(
            seq=self._seq,
            kind=kind,
            actor=actor,
            sim_time=self.guard.clock(),
            payload=payload,
            origin=origin,
        )
        self._events.append(ev)
        if len(self._events) > MAX_PREFIX:
            self._cap()
        return ev

    def _cap(self) -> None:
        """Drop the oldest event, keeping the first user message and tainted events."""
        first_user = next((e for e in self._events if e.kind == "user_message"), None)
        for i, e in enumerate(self._events):
            if e is first_user or (e.origin is not None and e.origin.markers):
                continue
            del self._events[i]
            return

    async def record_user_message(self, text: str) -> None:
        self._append("user_message", "user", {"text": text}, Origin(trust="user"))

    async def record_agent_message(self, text: str) -> None:
        self._append("agent_message", "agent", {"text": text}, Origin(trust="system"))

    async def record_tool_result(
        self,
        call_id: str,
        tool: str,
        result: object,
        *,
        untrusted: bool | None = None,
        source: str | None = None,
        ok: bool = True,
    ) -> None:
        if untrusted is None:
            trust = self.guard.origin_trust(tool)
        else:
            trust = "untrusted_external" if untrusted else "system"
        origin = Origin(trust=trust, source=(source or tool) if trust != "system" else source)
        self._append(
            "tool_result",
            "tool",
            {"call_id": call_id, "tool": tool, "ok": ok, "result": result},
            origin,
        )

    @contextlib.asynccontextmanager
    async def active(self) -> AsyncIterator[Session]:
        """Make this the current session for `Guard.wrap`ped tools in this task."""
        from .wrap import CURRENT

        token = CURRENT.set(self)
        try:
            yield self
        finally:
            CURRENT.reset(token)

    # -- checks -----------------------------------------------------------------------------

    async def check_tool_call(
        self, tool: str, args: Json, *, call_id: str | None = None
    ) -> GatewayDecision:
        return await self._check(
            "tool_call",
            ProposedAction(kind="tool_call", tool=tool, args=args),
            tool=tool,
            args=args,
            call_id=call_id or new_id("call"),
        )

    async def check_output(self, text: str) -> GatewayDecision:
        """A `redact` decision carries the replacement text in `decision.modified["text"]`."""
        return await self._check(
            "output", ProposedAction(kind="agent_message", text=text), tool=None, args=None
        )

    async def _check(
        self,
        kind: Literal["tool_call", "output"],
        proposed: ProposedAction,
        *,
        tool: str | None,
        args: Json | None,
        call_id: str | None = None,
    ) -> GatewayDecision:
        g = self.guard
        t0 = perf_counter_ns()
        policy, engine, severities = g.snapshot()
        mode = cast(Literal["shadow", "enforce"], g.mode or policy.mode)
        guard_error: str | None = None
        try:
            prefix = PrefixView.model_construct(
                events=self._events,
                initial_world=None,
                world=None,
                canaries=[],
                tool_risk=g.tool_risk,
                honeytools=[],
            )
            decided = engine.decide(prefix, proposed)
        except Exception as e:
            guard_error = f"{type(e).__name__}: {e}"[:200]
            log.warning("gateway: policy evaluation failed (%s)", guard_error)
            decided = (
                GatewayDecision(action="block", message="policy engine unavailable")
                if policy.fail == "closed"
                else GatewayDecision(action="allow")
            )
        engine_action = decided.action
        enforce = mode == "enforce"
        final = decided
        approval: ApprovalInfo | None = None
        waited_ns = 0

        if not enforce:
            if decided.action != "allow":
                final = decided.model_copy(update={"action": "allow", "modified": None})
        elif decided.action == "require_approval":
            approval = ApprovalInfo(id=new_id("gap"))
            record = self._record(
                kind, tool, args, decided, "require_approval", mode, enforce, None, policy,
                severities, approval, 0, guard_error,
            )  # fmt: skip
            w0 = perf_counter_ns()
            outcome, error = await self._approve(decided, record)
            waited_ns = perf_counter_ns() - w0
            guard_error = guard_error or error
            approval = ApprovalInfo(id=approval.id, outcome=outcome)
            allowed = outcome == "approved" or (outcome == "expired" and g.on_timeout == "allow")
            if allowed:
                final = GatewayDecision(
                    action="allow",
                    rule_id=decided.rule_id,
                    message=decided.message,
                    evidence=decided.evidence,
                    undetermined=decided.undetermined,
                )
            else:
                final = GatewayDecision(
                    action="block",
                    rule_id=decided.rule_id,
                    message=f"approval {outcome}: {decided.message or decided.rule_id}",
                    evidence=decided.evidence,
                    undetermined=decided.undetermined,
                )

        # The prefix grows after the decision, with what actually goes ahead.
        if final.action != "block":
            if kind == "tool_call":
                sent = (final.modified or {}).get("args", args) if final.modified else args
                self._append(
                    "tool_call",
                    "agent",
                    {"call_id": call_id, "tool": tool, "args": sent or {}, "via": "wired"},
                    Origin(trust="system"),
                )
            else:
                text = (final.modified or {}).get("text", proposed.text)
                self._append("agent_message", "agent", {"text": text}, Origin(trust="system"))

        overhead_us = (perf_counter_ns() - t0 - waited_ns) // 1000
        would_have = engine_action if (not enforce and engine_action != "allow") else None
        if not enforce:
            action = "allow"
        elif engine_action == "require_approval":
            action = "require_approval"  # `approval.outcome` says how it ended
        else:
            action = final.action
        record = self._record(
            kind, tool, args, final, action, mode, enforce, would_have, policy, severities,
            approval, overhead_us, guard_error,
        )  # fmt: skip
        await g.emit(record)
        return final

    def _record(
        self,
        kind: Literal["tool_call", "output"],
        tool: str | None,
        args: Json | None,
        d: GatewayDecision,
        action: str,
        mode: Literal["shadow", "enforce"],
        enforce: bool,
        would_have: str | None,
        policy,
        severities: dict[str, str],
        approval: ApprovalInfo | None,
        overhead_us: int,
        guard_error: str | None,
    ) -> DecisionRecord:
        g = self.guard
        return DecisionRecord(
            id=new_id("gdc"),
            ts=g.clock(),
            session_id=self.session_id,
            agent_id=g.agent_id,
            policy_id=policy.id,
            policy_version=policy.version,
            mode=mode,
            kind=kind,
            tool=tool,
            args=render_args(args, g.log_args) if args is not None else None,
            action=action,  # type: ignore[arg-type]
            enforced=enforce,
            would_have=would_have,  # type: ignore[arg-type]
            rule_id=d.rule_id,
            severity=severities.get(d.rule_id) if d.rule_id else None,  # type: ignore[arg-type]
            message=d.message,
            evidence=render_evidence(d.evidence, g.log_args),
            approval=approval,
            overhead_us=overhead_us,
            guard_error=guard_error,
        )

    async def _approve(
        self, d: GatewayDecision, record: DecisionRecord
    ) -> tuple[Literal["approved", "denied", "expired"], str | None]:
        g = self.guard
        if g.approvals is None:
            return "denied", "no approval handler configured"
        try:
            res = await asyncio.wait_for(g.approvals.request(d, record), g.approval_timeout_s)
        except (TimeoutError, ApprovalExpired):
            return "expired", None
        except Exception as e:  # transport trouble follows on_timeout
            log.warning("gateway: approval transport error (%s)", type(e).__name__)
            return "expired", f"approval transport: {type(e).__name__}: {e}"[:200]
        return ("approved" if res == "approved" else "denied"), None
