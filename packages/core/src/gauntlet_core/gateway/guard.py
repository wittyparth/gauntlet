"""The guard (P4-2): policy + mode + sink + approvals, and the factory for sessions."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from gauntlet_core.ids import new_id
from gauntlet_core.policy import PolicyEngine
from gauntlet_core.schema import Policy, load_yaml
from gauntlet_core.validate import walk_check

from .approvals import ApprovalHandler
from .classifier import DETECTOR_NAME, OriginRule, OriginRules, warm_up
from .decision import DecisionRecord, LogArgs
from .session import Session
from .sinks import DecisionSink
from .wrap import wrap_tool

__all__ = ["Guard", "utcnow"]

log = logging.getLogger("gauntlet.gateway")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Guard:
    """Loads a policy (an object or a YAML path; it must be prefix-evaluable or loading fails)
    and hands out sessions. `mode` overrides the policy's own mode. In `shadow` nothing is
    blocked, modified or held; the record carries `enforced=False` and `would_have`."""

    def __init__(
        self,
        policy: Policy | str | Path,
        *,
        mode: Literal["shadow", "enforce"] | None = None,
        sink: DecisionSink | None = None,
        approvals: ApprovalHandler | None = None,
        agent_id: str | None = None,
        clock: Callable[[], datetime] = utcnow,
        log_args: LogArgs = "redacted",
        approval_timeout_s: float = 300.0,
        on_timeout: Literal["deny", "allow"] = "deny",
        on_block: Literal["raise", "return"] = "raise",
        origin_rules: Sequence[OriginRule | str | dict[str, Any]] = (),
        use_origin_defaults: bool = True,
        tool_risk: dict[str, str] | None = None,
    ) -> None:
        self.mode = mode
        self.sink = sink
        self.approvals = approvals
        self.agent_id = agent_id
        self.clock = clock
        self.log_args: LogArgs = log_args
        self.approval_timeout_s = approval_timeout_s
        self.on_timeout = on_timeout
        self.on_block = on_block
        self.origin_rules = OriginRules(
            origin_rules, defaults=OriginRules().defaults if use_origin_defaults else ()
        )
        self.tool_risk: dict[str, str] = dict(tool_risk or {})
        self._untrusted_tools: set[str] = set()
        self.sink_errors = 0
        self._state = self._load(policy)

    # -- policy ----------------------------------------------------------------------------

    @staticmethod
    def _load(policy: Policy | str | Path) -> tuple[Policy, PolicyEngine, dict[str, str]]:
        doc = policy if isinstance(policy, Policy) else load_yaml(Policy, policy)
        engine = PolicyEngine(doc)  # raises ValueError when a rule cannot be evaluated live
        if any(
            n.type == "detector" and n.name == DETECTOR_NAME
            for r in doc.rules
            for n in walk_check(r.when)
        ):
            warm_up()  # load the model now, not on the first call
        return doc, engine, {r.id: r.severity for r in doc.rules}

    def reload(self, policy: Policy | str | Path) -> None:
        """Swap the policy atomically; sessions see it on their next call."""
        self._state = self._load(policy)

    def snapshot(self) -> tuple[Policy, PolicyEngine, dict[str, str]]:
        return self._state

    @property
    def policy(self) -> Policy:
        return self._state[0]

    # -- sessions and tools ----------------------------------------------------------------

    def session(self, session_id: str | None = None, *, user_id: str | None = None) -> Session:
        return Session(self, session_id or new_id("ses"), user_id)

    def origin_trust(self, tool: str) -> Literal["system", "user", "untrusted_external"]:
        """Trust of a tool's results: configured rules (first match), then
        `wrap(untrusted_output=True)`, then the conservative default globs, else system."""
        configured = self.origin_rules.configured(tool)
        if configured is not None:
            return configured
        if tool in self._untrusted_tools:
            return "untrusted_external"
        return self.origin_rules.match(tool) or "system"

    def is_untrusted_tool(self, tool: str) -> bool:
        return self.origin_trust(tool) == "untrusted_external"

    def wrap(
        self,
        fn: Callable[..., Any],
        *,
        tool: str | None = None,
        risk: str | None = None,
        untrusted_output: bool = False,
    ) -> Callable[..., Any]:
        """Guard a sync or async tool function. The returned callable is always async and
        needs a current session (`async with session.active()`) or a `session=` argument."""
        name = tool or getattr(fn, "__name__", "tool")
        if risk is not None:
            self.tool_risk[name] = risk
        if untrusted_output:
            self._untrusted_tools.add(name)
        return wrap_tool(self, fn, name, untrusted_output)

    def tool(
        self, *, name: str | None = None, risk: str | None = None, untrusted_output: bool = False
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            return self.wrap(fn, tool=name, risk=risk, untrusted_output=untrusted_output)

        return deco

    # -- records ---------------------------------------------------------------------------

    async def emit(self, record: DecisionRecord) -> None:
        """Never raises: sink trouble is counted and logged."""
        if self.sink is None:
            return
        try:
            await self.sink.write(record)
        except Exception as e:
            self.sink_errors += 1
            log.warning("gateway: sink write failed (%s)", type(e).__name__)
