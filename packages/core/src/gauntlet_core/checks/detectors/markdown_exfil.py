"""Markdown / HTML image (and link) exfiltration: data smuggled out in a URL."""

from __future__ import annotations

import re
from collections.abc import Sequence
from urllib.parse import urlparse

from .types import Hit, clip

_IMG = re.compile(r"!\[[^\]]{0,200}\]\(\s*<?([^)\s>]{1,2000})>?[^)]{0,200}\)")
_HTML_IMG = re.compile(r"""<img\b[^>]{0,500}?\bsrc\s*=\s*["']?([^"'\s>]{1,2000})""", re.IGNORECASE)
_REF_IMG = re.compile(r"!\[[^\]]{0,200}\]\[([^\]]{1,100})\]")
_REF_DEF = re.compile(r"^[ ]{0,3}\[([^\]]{1,100})\]:[ \t]*<?(\S{1,2000}?)>?[ \t]*$", re.MULTILINE)
_LINK = re.compile(r"(?<!!)\[[^\]]{0,200}\]\(\s*<?([^)\s>]{1,2000})")
_RUN = re.compile(r"[A-Za-z0-9+/=_-]{32,}")
_HEX = re.compile(r"[0-9a-fA-F]+")


def _host_allowed(host: str, allow: Sequence[str]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == d.lower() or host.endswith("." + d.lower()) for d in allow)


def _has_encoded_run(url: str) -> bool:
    """A 32+ character base64 or hex-like run. Slugs made only of letters and hyphens are not
    flagged: a run must be hex, or mix letters with digits."""
    p = urlparse(url)
    for part in (p.path, p.query, p.fragment):
        for m in _RUN.finditer(part):
            run = m.group()
            if _HEX.fullmatch(run):
                return True
            if any(c.isdigit() for c in run) and any(c.isalpha() for c in run):
                return True
    return False


def detect_markdown_image_exfil(
    text: str, *, allow_domains: Sequence[str] = (), min_query_chars: int = 16
) -> list[Hit]:
    refs = {m.group(1).lower(): m.group(2) for m in _REF_DEF.finditer(text)}
    candidates: list[tuple[int, int, str, bool]] = []  # start, end, url, is_image
    for m in _IMG.finditer(text):
        candidates.append((m.start(1), m.end(1), m.group(1), True))
    for m in _HTML_IMG.finditer(text):
        candidates.append((m.start(1), m.end(1), m.group(1), True))
    for m in _REF_IMG.finditer(text):
        url = refs.get(m.group(1).lower())
        if url:
            candidates.append((m.start(), m.end(), url, True))
    for m in _LINK.finditer(text):
        candidates.append((m.start(1), m.end(1), m.group(1), False))

    hits: list[Hit] = []
    seen: set[tuple[int, int]] = set()
    for start, end, url, is_image in sorted(candidates):
        if (start, end) in seen:
            continue
        seen.add((start, end))
        p = urlparse(url)
        label = None
        if (
            is_image
            and p.hostname
            and not _host_allowed(p.hostname, allow_domains)
            and max(len(p.query), len(p.fragment)) >= min_query_chars
        ):
            label = "image_query_exfil"
        if label is None and _has_encoded_run(url):
            label = "encoded_url"
        if label:
            hits.append(Hit(label, clip(url), None, start, end))
    return hits
