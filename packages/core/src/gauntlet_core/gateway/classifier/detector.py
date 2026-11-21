"""The `injection_classifier` detector (P4-4). Prefix-evaluable: it reads `tool_result` events
(untrusted-origin ones by default) and answers from a classifier score, or says "undetermined"
when it ran out of its latency budget or has no model."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from gauntlet_core.checks.detectors import register
from gauntlet_core.schema import CheckResult, Event, Evidence, Trajectory

from .model import ClassifierUnavailable, InjectionClassifier, default_classifier

__all__ = [
    "DETECTOR_NAME",
    "LRU_SIZE",
    "configure",
    "detect_injection",
    "split_windows",
    "warm_up",
    "windows",
]

DETECTOR_NAME = "injection_classifier"
LRU_SIZE = 10_000
BATCH = 8
UNAVAILABLE = "injection_classifier:unavailable"
INCOMPLETE = "injection_classifier:latency_budget"
log = logging.getLogger("gauntlet.gateway")

_classifier: InjectionClassifier | None = None
_clock: Callable[[], float] = time.monotonic
_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()  # text hash -> (score, best window)


def configure(
    classifier: InjectionClassifier | None = None,
    *,
    clock: Callable[[], float] | None = None,
    reset: bool = True,
) -> None:
    """Install the classifier (and, in tests, a clock). Clears the score cache by default."""
    global _classifier, _clock
    _classifier = classifier
    if clock is not None:
        _clock = clock
    if reset:
        _cache.clear()


def warm_up() -> bool:
    """Load the default classifier now (called when a Guard's policy uses the detector), so
    the first call does not pay for it. A missing model is logged, never raised."""
    global _classifier
    if _classifier is not None:
        return True
    try:
        _classifier = default_classifier()
    except ClassifierUnavailable as e:
        log.warning("injection classifier not loaded: %s", e)
        return False
    return True


def windows(n_tokens: int, max_tokens: int, stride: int) -> list[tuple[int, int]]:
    """Token ranges [start, end): windows of `max_tokens`, starting every `stride` tokens."""
    if n_tokens <= 0:
        return []
    if n_tokens <= max_tokens:
        return [(0, n_tokens)]
    step = max(1, stride)
    out: list[tuple[int, int]] = []
    start = 0
    while True:
        end = min(start + max_tokens, n_tokens)
        out.append((start, end))
        if end >= n_tokens:
            return out
        start += step


def split_windows(text: str, max_tokens: int, stride: int) -> list[str]:
    """Windows of whitespace tokens (an approximation of model tokens, deliberately short of
    the model limit by using the same unit for the window and the stride)."""
    toks = text.split()
    return [" ".join(toks[a:b]) for a, b in windows(len(toks), max_tokens, stride)]


def _text_of(e: Event) -> str:
    res = e.payload.get("result")
    if res is None:
        res = e.payload.get("error", "")
    return res if isinstance(res, str) else json.dumps(res, ensure_ascii=False, default=str)


def _scored(
    clf: InjectionClassifier,
    text: str,
    max_tokens: int,
    stride: int,
    threshold: float,
    deadline: float,
    clock: Callable[[], float],
) -> tuple[float, str] | None:
    """(max score, best window), or None when the budget ran out before an answer."""
    key = hashlib.sha256(f"{max_tokens}:{stride}:{text}".encode()).hexdigest()
    hit = _cache.get(key)
    if hit is not None:
        _cache.move_to_end(key)
        return hit
    wins = split_windows(text, max_tokens, stride)
    best, best_win = 0.0, ""
    for i in range(0, len(wins), BATCH):
        chunk = wins[i : i + BATCH]
        for s, w in zip(clf.score(chunk), chunk, strict=True):
            if s > best:
                best, best_win = s, w
        if best >= threshold:
            break  # decided; the rest cannot change the answer
        if i + BATCH < len(wins) and clock() > deadline:
            return None
    _cache[key] = (best, best_win)
    if len(_cache) > LRU_SIZE:
        _cache.popitem(last=False)
    return best, best_win


@register(DETECTOR_NAME)
def detect_injection(traj: Trajectory, params: Mapping[str, Any]) -> CheckResult:
    clf, clock = _classifier, _clock
    if clf is None:
        return CheckResult(holds=False, needs_judge=[UNAVAILABLE])
    threshold = float(params.get("threshold", 0.9))
    scope = params.get("scope", "untrusted")
    max_tokens = int(params.get("max_tokens", 512))
    stride = int(params.get("stride", 256))
    deadline = clock() + float(params.get("latency_budget_ms", 50)) / 1000
    evidence: list[Evidence] = []
    incomplete = False
    last = traj.events[-1] if traj.events else None
    candidates: Sequence[Event] = [
        e
        for e in traj.events
        if (
            e.kind == "tool_result"
            and (
                scope == "all" or (e.origin is not None and e.origin.trust == "untrusted_external")
            )
        )
        or (scope == "all" and e is last and e.kind == "agent_message")
    ]
    for e in candidates:
        text = _text_of(e) if e.kind == "tool_result" else str(e.payload.get("text", ""))
        if not text.strip():
            continue
        got = _scored(clf, text, max_tokens, stride, threshold, deadline, clock)
        if got is None:
            incomplete = True
            break
        score, window = got
        if score >= threshold:
            evidence.append(
                Evidence(seq=e.seq, quote=window[:200], note=f"injection score {score:.2f}")
            )
    if evidence:
        return CheckResult(holds=True, evidence=evidence)
    return CheckResult(holds=False, needs_judge=[INCOMPLETE] if incomplete else [])
