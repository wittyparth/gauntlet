"""PII detector: email, phone, ssn, card (Luhn), iban (mod 97)."""

from __future__ import annotations

import re
from collections.abc import Sequence

from .types import Hit, clip

ALL_KINDS: tuple[str, ...] = ("email", "phone", "ssn", "card", "iban")

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,}")
_E164 = re.compile(r"(?<![\w+])\+\d{8,15}(?!\d)")
# North-American numbers need a separator or parentheses: bare 10-digit runs (order numbers,
# timestamps) are not flagged, and an identifier prefix (`ORD-`, `#`) disqualifies the match.
_NA = re.compile(
    r"(?<![\w#-])(?:\(\d{3}\)[ .-]?|\d{3}[ .-])\d{3}[ .-]?\d{4}(?!\d)"
    r"|(?<![\w#-])\d{3}\d{3}[.-]\d{4}(?!\d)"
)
_SSN = re.compile(r"(?<![\d-])(\d{3})-(\d{2})-(\d{4})(?![\d-])")
_CARD = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def iban_ok(s: str) -> bool:
    s = s.replace(" ", "")
    if not 15 <= len(s) <= 34:
        return False
    moved = s[4:] + s[:4]
    num = "".join(str(int(c, 36)) for c in moved)
    return int(num) % 97 == 1


def _ssn_ok(m: re.Match[str]) -> bool:
    area, group, serial = m.group(1), m.group(2), m.group(3)
    return not (area in ("000", "666") or area.startswith("9") or group == "00" or serial == "0000")


def detect_pii(
    text: str, *, kinds: Sequence[str] = ALL_KINDS, allow: Sequence[str] = ()
) -> list[Hit]:
    unknown = set(kinds) - set(ALL_KINDS)
    if unknown:
        raise ValueError(f"unknown pii kinds: {sorted(unknown)}")
    found: list[tuple[int, int, str]] = []

    def add(kind: str, m: re.Match[str]) -> None:
        found.append((m.start(), m.end(), kind))

    if "email" in kinds:
        for m in _EMAIL.finditer(text):
            add("email", m)
    if "ssn" in kinds:
        for m in _SSN.finditer(text):
            if _ssn_ok(m):
                add("ssn", m)
    if "card" in kinds:
        for m in _CARD.finditer(text):
            digits = re.sub(r"\D", "", m.group())
            if 13 <= len(digits) <= 19 and luhn_ok(digits):
                add("card", m)
    if "iban" in kinds:
        for m in _IBAN.finditer(text):
            if iban_ok(m.group()):
                add("iban", m)
    if "phone" in kinds:
        for rx in (_E164, _NA):
            for m in rx.finditer(text):
                add("phone", m)
    allowed = set(allow)
    hits: list[Hit] = []
    taken: list[tuple[int, int]] = []
    for start, end, kind in sorted(found, key=lambda t: (t[0], -(t[1] - t[0]))):
        if any(start < e and s < end for s, e in taken):
            continue
        matched = text[start:end]
        if matched in allowed:
            continue
        taken.append((start, end))
        hits.append(Hit(kind, clip(matched), None, start, end))
    return hits
