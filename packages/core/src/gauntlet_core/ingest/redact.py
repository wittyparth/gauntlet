"""Redaction of production text before anything is stored (P5-1).

Typed, consistent tokens (`[EMAIL_a1b2c3]`): the suffix is a keyed hash of the value within a
scope (workspace and conversation), so the same value gets the same token across batches and
processes, and the value cannot be recovered from the token without the key. No mapping is kept.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from gauntlet_core.checks.detectors.pii import detect_pii
from gauntlet_core.checks.detectors.secret import detect_secret

__all__ = ["SECRET_KEYS", "RedactionConfig", "Redactor"]

SECRET_KEYS = re.compile(
    r"(?i)(^|[._-])(authorization|api[_-]?key|x-api-key|password|passwd|secret|token|cookie)($|[._-])"
)


_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def is_secret_key(key: str) -> bool:
    """`accessToken` and `clientSecret` count as well as `access_token`."""
    return bool(SECRET_KEYS.search(_CAMEL.sub("_", key)))


@dataclass(frozen=True)
class RedactionConfig:
    extra_patterns: Sequence[tuple[str, str]] = ()  # (label, regex)


@dataclass
class Redactor:
    key: bytes
    scope: str = ""
    config: RedactionConfig = field(default_factory=RedactionConfig)
    counts: Counter[str] = field(default_factory=Counter)

    def _token(self, label: str, value: str) -> str:
        digest = hmac.new(self.key, f"{self.scope}\0{label}\0{value}".encode(), hashlib.sha256)
        return f"[{label.upper()}_{digest.hexdigest()[:6]}]"

    def _spans(self, text: str) -> list[tuple[int, int, str]]:
        spans: list[tuple[int, int, str]] = []
        for h in detect_pii(text):
            if h.start is not None and h.end is not None:
                spans.append((h.start, h.end, h.label))
        for h in detect_secret(text):
            if h.start is not None and h.end is not None:
                spans.append((h.start, h.end, "secret"))
        for label, rx in self.config.extra_patterns:
            spans += [(m.start(), m.end(), label) for m in re.finditer(rx, text)]
        spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
        merged: list[tuple[int, int, str]] = []
        for s in spans:
            if merged and s[0] < merged[-1][1]:
                if s[1] > merged[-1][1]:  # it runs past the earlier span: cover the tail too
                    merged[-1] = (merged[-1][0], s[1], merged[-1][2])
                continue
            merged.append(s)
        return merged

    def redact_text(self, text: str) -> str:
        out, pos = [], 0
        for start, end, label in self._spans(text):
            out.append(text[pos:start])
            out.append(self._token(label, text[start:end]))
            self.counts[label] += 1
            pos = end
        out.append(text[pos:])
        return "".join(out)

    def redact_json(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for k, v in value.items():
                if isinstance(k, str) and is_secret_key(k):
                    self.counts["secret_key"] += 1
                    continue  # secret-named keys are removed, not masked
                out[self.redact_text(k) if isinstance(k, str) else k] = self.redact_json(v)
            return out
        if isinstance(value, list | tuple):
            return [self.redact_json(v) for v in value]
        return value
