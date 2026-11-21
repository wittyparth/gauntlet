"""Origin rules (P4-4): which tools' results count as untrusted content."""

from __future__ import annotations

from collections.abc import Sequence
from fnmatch import fnmatchcase
from typing import Any, Literal

from gauntlet_core.schema import Model

__all__ = ["DEFAULT_ORIGIN_RULES", "OriginRule", "OriginRules", "Trust"]

Trust = Literal["system", "user", "untrusted_external"]


class OriginRule(Model):
    tool: str  # glob
    trust: Trust


DEFAULT_ORIGIN_RULES: tuple[OriginRule, ...] = tuple(
    OriginRule(tool=g, trust="untrusted_external")
    for g in (
        "*fetch*", "*browse*", "*search*", "*read_email*", "*inbox*", "*web*", "*scrape*",
        "*download*",
    )
)  # fmt: skip


def _coerce(item: Any) -> OriginRule:
    if isinstance(item, OriginRule):
        return item
    if isinstance(item, str):  # a bare glob means untrusted
        return OriginRule(tool=item, trust="untrusted_external")
    return OriginRule.model_validate(item)


class OriginRules:
    """First match wins. The configured rules come first; the conservative defaults only
    apply to a tool no configured rule names."""

    def __init__(
        self,
        rules: Sequence[OriginRule | str | dict[str, Any]] = (),
        *,
        defaults: Sequence[OriginRule] = DEFAULT_ORIGIN_RULES,
    ) -> None:
        self.rules = [_coerce(r) for r in rules]
        self.defaults = list(defaults)

    def match(self, tool: str) -> Trust | None:
        for r in [*self.rules, *self.defaults]:
            if fnmatchcase(tool, r.tool):
                return r.trust
        return None

    def configured(self, tool: str) -> Trust | None:
        for r in self.rules:
            if fnmatchcase(tool, r.tool):
                return r.trust
        return None
