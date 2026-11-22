"""Anonymisation of a production conversation for conversion (P5-2).

Ingest already redacted PII, secrets and cards into typed tokens. This pass turns what is left
into seeded synthetic stand-ins: the typed tokens, names, order and account numbers, street
addresses. Replacement is consistent (the same value gets the same stand-in, within and across
conversations for one seed) and keeps no mapping, only a hash of it. Then a residual scan lists
what could not be replaced; values in it are kept in memory for the caller's k-anonymity check
and must never be stored or logged."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from gauntlet_core.checks.detectors.pii import detect_pii
from gauntlet_core.checks.detectors.secret import detect_secret
from gauntlet_core.schema import Event

__all__ = [
    "Anonymised",
    "Residual",
    "anonymise",
    "anonymise_json",
    "entropy",
    "residual_scan",
]

FIRST = ["Alex", "Sam", "Jordan", "Taylor", "Casey", "Morgan", "Riley", "Avery", "Quinn", "Robin"]
LAST = ["Example", "Sample", "Testfield", "Demoworth", "Placeholder", "Mockridge", "Fakeman"]
STREETS = ["Example Street", "Sample Avenue", "Demo Road", "Test Lane"]

_TOKEN = re.compile(r"\[(EMAIL|PHONE|CARD|SECRET|SSN|IBAN)_([0-9a-f]{6})\]")
_ANY_TOKEN = re.compile(r"\[[A-Z_]+_[0-9a-f]{6}\]")
_NAME_CUE = re.compile(
    r"(?:my name is|this is|i am|i'm|name:|hi|hello|dear|thanks|thank you)[,:]?\s+"
    r"([A-Z][a-z]{2,}(?:\s[A-Z][a-z]{2,})?)\b"
)
_NUMBER = re.compile(
    r"\b((?:ord|order|acct|account|cust|customer|inv|invoice|ticket|case)[-_ #:]*)(\d{3,})\b",
    re.IGNORECASE,
)
_ADDRESS = re.compile(
    r"\b\d{1,5}\s+[A-Z][a-z]+(?:\s[A-Z][a-z]+)?\s(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr)\b"
)
_LONG = re.compile(r"[A-Za-z0-9_+/=-]{16,}")
_NON_PERSON = {"thanks", "there", "again", "please", "support", "team", "everyone"}


@dataclass(frozen=True)
class Residual:
    kind: str
    value: str = field(repr=False)  # in memory only


@dataclass
class Anonymised:
    events: list[Event]
    replacements: int
    mapping_hash: str
    residual: list[Residual]
    synthetic: set[str] = field(default_factory=set, repr=False)  # stand-ins to allow in scans


def _h(seed: int, kind: str, value: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}:{kind}:{value}".encode()).digest()[:6], "big")


def entropy(s: str) -> float:
    counts = Counter(s)
    return -sum(c / len(s) * math.log2(c / len(s)) for c in counts.values()) if s else 0.0


class _Replacer:
    def __init__(self, seed: int, texts: Sequence[str] = ()) -> None:
        self.seed = seed
        self.names: dict[str, str] = {}  # learned name (full or part) -> stand-in
        self.digits: dict[str, str] = {}  # learned identifier digits -> stand-in digits
        self._learn(texts)
        self.count = 0
        self.pairs: set[tuple[str, str]] = set()
        self.synthetic: set[str] = set()

    def _stand_in_name(self, who: str) -> str:
        n = _h(self.seed, "name", who)
        full = f"{FIRST[n % len(FIRST)]} {LAST[(n // 10) % len(LAST)]}"
        return full if " " in who else full.split()[0]

    def _learn(self, texts: Sequence[str]) -> None:
        """Names and identifiers announced by a cue anywhere in the conversation are replaced
        everywhere in it, including in tool arguments and results that carry no cue."""
        for t in texts:
            for m in _NAME_CUE.finditer(t):
                who = m.group(1)
                if who.split()[0].lower() in _NON_PERSON:
                    continue
                full = self._stand_in_name(who)
                self.names[who] = full
                if " " in who:
                    first, last = who.split(), full.split()
                    self.names.setdefault(first[0], last[0])
                    self.names.setdefault(first[1], last[1])
            for m in _NUMBER.finditer(t):
                digits = m.group(2)
                n = _h(self.seed, "number", digits)
                self.digits[digits] = str(n).zfill(len(digits))[-len(digits) :]

    def _note(self, kind: str, original: str, stand_in: str, allow: bool = False) -> str:
        self.count += 1
        self.pairs.add((hashlib.sha256(f"{kind}:{original}".encode()).hexdigest()[:16], stand_in))
        if allow:
            self.synthetic.add(stand_in)
        return stand_in

    def token(self, m: re.Match[str]) -> str:
        kind, _ = m.group(1), m.group(2)
        n = _h(self.seed, "token", m.group(0))
        if kind == "EMAIL":
            return self._note("email", m.group(0), f"user{n % 9000 + 1000}@example.test", True)
        return self._note(
            kind, m.group(0),
            {"PHONE": "[phone on file]", "CARD": "[card on file]", "SECRET": "[credential]",
             "SSN": "[id number]", "IBAN": "[bank account]"}[kind],
        )  # fmt: skip

    def bare(self, text: str) -> str:
        """Learned names and identifier digits wherever they appear on their own."""
        for who in sorted(self.names, key=len, reverse=True):
            pattern = rf"\b{re.escape(who)}\b"
            text, n = re.subn(pattern, self.names[who], text)
            for _ in range(n):
                self._note("name", who, self.names[who])
        for digits, stand_in in self.digits.items():
            text, n = re.subn(rf"(?<!\d){digits}(?!\d)", stand_in, text)
            for _ in range(n):
                self._note("number", digits, stand_in)
        return text

    def address(self, m: re.Match[str]) -> str:
        n = _h(self.seed, "address", m.group(0))
        return self._note("address", m.group(0), f"{n % 90 + 10} {STREETS[n % len(STREETS)]}")

    def text(self, text: str) -> str:
        text = _TOKEN.sub(self.token, text)
        text = _ADDRESS.sub(self.address, text)
        return self.bare(text)


def _map(value: Any, fn) -> Any:
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, dict):
        return {(fn(k) if isinstance(k, str) else k): _map(v, fn) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_map(v, fn) for v in value]
    return value


def anonymise_json(value: Any, *, seed: int) -> tuple[Any, Anonymised]:
    r = _Replacer(seed, _strings_of(value))
    out = _map(value, r.text)
    return out, Anonymised([], r.count, _mapping_hash(r), [], r.synthetic)


def _mapping_hash(r: _Replacer) -> str:
    body = "\n".join(f"{a}->{b}" for a, b in sorted(r.pairs))
    return hashlib.sha256(body.encode()).hexdigest()


_SYNTH_EMAIL = re.compile(r"user\d{4}@example\.test")


def _strings_of(value: Any) -> list[str]:
    out: list[str] = []
    _map(value, lambda s: out.append(s) or s)
    return out


def residual_scan(texts: Sequence[str], *, allow: set[str]) -> list[Residual]:
    """What a conversion must not carry: PII and secrets (other than known stand-ins), unreplaced
    typed tokens, and long high-entropy tokens."""
    out: list[Residual] = []
    allow = set(allow)
    for t in texts:
        allow.update(_SYNTH_EMAIL.findall(t))  # our own stand-ins are not leaks
        out += [Residual(h.label, t[h.start : h.end]) for h in detect_pii(t, allow=tuple(allow))
                if h.start is not None and h.end is not None]  # fmt: skip
        out += [Residual("secret", t[h.start : h.end]) for h in detect_secret(t)
                if h.start is not None and h.end is not None]  # fmt: skip
        out += [Residual("token", m.group(0)) for m in _ANY_TOKEN.finditer(t)]
        for m in _LONG.finditer(t):
            v = m.group(0)
            if (
                entropy(v) >= 3.5
                and any(c.isdigit() for c in v)
                and any(c.isalpha() for c in v)
                and v not in allow
            ):
                out.append(Residual("high_entropy", v))
    return out


def _texts(events: Sequence[Event]) -> list[str]:
    out: list[str] = []

    def walk(v: Any) -> None:
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    for e in events:
        walk(e.payload)
    return out


def anonymise(events: Sequence[Event], *, seed: int) -> Anonymised:
    r = _Replacer(seed, _texts(events))
    new = [e.model_copy(update={"payload": _map(e.payload, r.text)}) for e in events]
    return Anonymised(
        events=new,
        replacements=r.count,
        mapping_hash=_mapping_hash(r),
        residual=residual_scan(_texts(new), allow=r.synthetic),
        synthetic=r.synthetic,
    )
