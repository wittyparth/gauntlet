"""`embed:<placement>`: turn the payload into document content (the harness picks the document)."""

from __future__ import annotations

import json
import random

from gauntlet_core.llm import Gateway
from gauntlet_core.schema import Attack

from .base import derive

__all__ = ["PLACEMENTS", "EmbedMutation", "render"]


def render(placement: str, text: str) -> str:
    if placement == "body":
        return text
    if placement == "footer":
        return f"\n\n-- \n{text}"
    if placement == "html_comment":
        return f"<!-- {text} -->"
    if placement == "hidden_text":
        return f'<span style="display:none">{text}</span>'
    if placement == "metadata":
        return json.dumps({"note": text}, ensure_ascii=False)
    raise ValueError(f"unknown placement {placement!r}")


PLACEMENTS = ("body", "footer", "html_comment", "hidden_text", "metadata")


class EmbedMutation:
    def __init__(self, placement: str) -> None:
        if placement not in PLACEMENTS:
            raise ValueError(f"unknown placement {placement!r}")
        self.placement = placement
        self.name = f"embed:{placement}"

    async def apply(
        self, attack: Attack, *, rng: random.Random, gateway: Gateway | None
    ) -> list[Attack]:
        if not isinstance(attack.payload, str):
            return []
        a = derive(
            attack,
            self.name,
            render(self.placement, attack.payload),
            extra_requires=("documents",),
            vector="document",
            target="{{document}}",
        )
        return [a] if a else []
