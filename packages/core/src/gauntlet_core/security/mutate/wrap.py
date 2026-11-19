"""`wrap:<id>`: frame the payload in one of the neutral templates in attacks/wrappers.yaml."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import yaml

from gauntlet_core.llm import Gateway
from gauntlet_core.schema import Attack
from gauntlet_core.security.taxonomy import DEFAULT_TAXONOMY_PATH

from .base import derive

__all__ = ["DEFAULT_WRAPPERS_PATH", "WrapMutation", "Wrapper", "load_wrappers"]

DEFAULT_WRAPPERS_PATH = DEFAULT_TAXONOMY_PATH.parent / "wrappers.yaml"
TOKEN = "{{payload}}"
MAX_WRAPPERS = 8
MAX_WORDS = 40


@dataclass(frozen=True)
class Wrapper:
    id: str
    template: str


def load_wrappers(path: Path | None = None) -> dict[str, Wrapper]:
    rows = yaml.safe_load(Path(path or DEFAULT_WRAPPERS_PATH).read_text()) or []
    if len(rows) > MAX_WRAPPERS:
        raise ValueError(f"at most {MAX_WRAPPERS} wrappers")
    out: dict[str, Wrapper] = {}
    for r in rows:
        tpl = str(r["template"])
        if tpl.count(TOKEN) != 1:
            raise ValueError(f"wrapper {r['id']!r} needs exactly one {TOKEN}")
        if len(tpl.replace(TOKEN, "").split()) > MAX_WORDS:
            raise ValueError(f"wrapper {r['id']!r} has more than {MAX_WORDS} words")
        out[r["id"]] = Wrapper(r["id"], tpl)
    return out


class WrapMutation:
    def __init__(self, wrapper_id: str, wrappers: dict[str, Wrapper] | None = None) -> None:
        self.wrapper = (wrappers or load_wrappers())[wrapper_id]
        self.name = f"wrap:{wrapper_id}"

    async def apply(
        self, attack: Attack, *, rng: random.Random, gateway: Gateway | None
    ) -> list[Attack]:
        if not isinstance(attack.payload, str):
            return []  # list payloads are multi-turn; framing one turn would change the plan
        a = derive(attack, self.name, self.wrapper.template.replace(TOKEN, attack.payload))
        return [a] if a else []
