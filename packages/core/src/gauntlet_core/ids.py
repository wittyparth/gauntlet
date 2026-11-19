"""Prefixed ULIDs: `run_01J...`. Sortable by creation time, monotonic within a process."""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable

__all__ = ["new_id"]

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_lock = threading.Lock()
_last_ms = -1
_last_rand = 0


def _encode(value: int, length: int) -> str:
    out = []
    for _ in range(length):
        out.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(out))


def new_id(prefix: str, *, now_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000) -> str:
    """Return `prefix_<26-char ULID>`. Within one millisecond the random part increments."""
    global _last_ms, _last_rand
    with _lock:
        ms = max(now_ms(), _last_ms)  # a clock that steps back must not break ordering
        if ms == _last_ms:
            _last_rand += 1
        else:
            _last_rand = secrets.randbits(79)  # top bit clear: headroom to increment
        _last_ms = ms
        return f"{prefix}_{_encode(ms, 10)}{_encode(_last_rand, 16)}"
