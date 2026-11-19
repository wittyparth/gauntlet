"""`{{...}}` placeholders in attack payloads and objectives."""

from __future__ import annotations

import re
from collections.abc import Mapping

__all__ = [
    "ALLOWED_PLACEHOLDERS",
    "PLACEHOLDER_RE",
    "extract_placeholders",
    "is_allowed_placeholder",
    "substitute",
]

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*(?::[A-Za-z0-9_.-]+)?)\s*\}\}")
ALLOWED_PLACEHOLDERS = frozenset(
    {"marker", "attacker_email", "attacker_url", "honeytool", "user_goal"}
)


def extract_placeholders(text: str) -> list[str]:
    """Placeholder names in order of appearance (with repeats)."""
    return PLACEHOLDER_RE.findall(text)


def is_allowed_placeholder(name: str) -> bool:
    return name in ALLOWED_PLACEHOLDERS or (
        name.startswith("canary:") and len(name) > len("canary:")
    )


def substitute(text: str, values: Mapping[str, str]) -> str:
    """Replace every placeholder; a placeholder with no value raises KeyError. Other braces
    are untouched."""

    def repl(m: re.Match[str]) -> str:
        return values[m.group(1)]

    return PLACEHOLDER_RE.sub(repl, text)
