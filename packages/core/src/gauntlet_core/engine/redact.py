"""Keeps secrets out of the journal. Runs on every event and effect before it is appended."""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = re.compile(r"(?i)^(authorization|api[-_]?key|x-api-key|password|secret|token)$")
_BEARER = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{16,}")


def redact(value: Any, secrets: tuple[str, ...] = ()) -> Any:
    """Return a copy of `value` with known secret values, bearer tokens and the values of
    sensitive-looking keys replaced. Canaries are not secrets and are left alone."""
    if isinstance(value, str):
        out = value
        for s in secrets:
            if s and len(s) >= 6:
                out = out.replace(s, REDACTED)
        return _BEARER.sub(f"Bearer {REDACTED}", out)
    if isinstance(value, dict):
        return {
            k: (REDACTED if isinstance(k, str) and _SENSITIVE_KEYS.match(k) else redact(v, secrets))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(v, secrets) for v in value]
    return value
