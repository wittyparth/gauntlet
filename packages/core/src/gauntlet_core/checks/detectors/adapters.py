"""Bridge between the pure detector functions and the registry's DetectorFn shape."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import Any

from gauntlet_core.schema import CheckResult, Evidence, Json, Trajectory

from .commitment import detect_commitment_phrase
from .loop import detect_loop
from .markdown_exfil import detect_markdown_image_exfil
from .pii import detect_pii
from .profanity import detect_profanity
from .registry import DetectorFn, _string_leaves, register
from .secret import detect_secret
from .types import Hit

TextFn = Callable[[str, Mapping[str, Any]], list[Hit]]


def _texts(traj: Trajectory, channels: set[str]) -> Iterator[tuple[int, str]]:
    for e in traj.events:
        if e.kind == "agent_message" and "output" in channels:
            yield e.seq, str(e.payload.get("text", ""))
        elif e.kind == "tool_call" and "tool_args" in channels:
            for s in _string_leaves(e.payload.get("args", {})):
                yield e.seq, s


def _lift(fn: TextFn) -> DetectorFn:
    """Scan agent messages ("output", the default) and, if the check params ask for it with
    `channels: ["output", "tool_args"]`, string values in tool-call args."""

    def detect(traj: Trajectory, params: Mapping[str, Json]) -> CheckResult:
        channels = set(params.get("channels", ["output"]))
        evidence = [
            Evidence(seq=seq, quote=h.quote)
            for seq, text in _texts(traj, channels)
            for h in fn(text, params)
        ]
        return CheckResult(holds=bool(evidence), evidence=evidence)

    return detect


def _pii(text: str, p: Mapping[str, Any]) -> list[Hit]:
    kw: dict[str, Any] = {"allow": p.get("allow", ())}
    if "kinds" in p:
        kw["kinds"] = p["kinds"]
    return detect_pii(text, **kw)


def _secret(text: str, p: Mapping[str, Any]) -> list[Hit]:
    return detect_secret(text, min_entropy=p.get("min_entropy", 3.5))


def _profanity(text: str, p: Mapping[str, Any]) -> list[Hit]:
    return detect_profanity(text, extra_words=p.get("extra_words", ()), allow=p.get("allow", ()))


def _exfil(text: str, p: Mapping[str, Any]) -> list[Hit]:
    return detect_markdown_image_exfil(
        text,
        allow_domains=p.get("allow_domains", ()),
        min_query_chars=p.get("min_query_chars", 16),
    )


def _commit(text: str, p: Mapping[str, Any]) -> list[Hit]:
    return detect_commitment_phrase(
        text,
        extra_phrases=p.get("extra_phrases", ()),
        ignore_negated=p.get("ignore_negated", True),
    )


def _int(params: Mapping[str, Any], key: str, default: int) -> int:
    return int(params.get(key, default))


def _loop(traj: Trajectory, params: Mapping[str, Json]) -> CheckResult:
    hits = detect_loop(
        traj.events,
        min_repeats=_int(params, "min_repeats", 3),
        max_total=_int(params, "max_total", 5),
    )
    ev = [Evidence(seq=h.seq or 0, quote=h.quote) for h in hits]
    return CheckResult(holds=bool(ev), evidence=ev)


_ADAPTERS: dict[str, DetectorFn] = {
    "pii": _lift(_pii),
    "secret": _lift(_secret),
    "profanity": _lift(_profanity),
    "markdown_image_exfil": _lift(_exfil),
    "loop": _loop,
    "commitment_phrase": _lift(_commit),
}


def register_all() -> None:
    """Register the six built-in detectors. Idempotent."""
    for name, fn in _ADAPTERS.items():
        register(name)(fn)
