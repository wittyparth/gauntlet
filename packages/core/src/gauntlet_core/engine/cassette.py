"""Cassettes: a journal exported as JSON Lines, and loaded back into a store for replay."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from gauntlet_core.schema import EffectRecord, Event

from .store import JournalSnapshot, MemoryJournalStore

FORMAT = "gauntlet-cassette/1"


def dump_cassette(journal: JournalSnapshot, manifest: dict[str, Any] | None = None) -> str:
    lines: list[dict[str, Any]] = [{"t": "header", "format": FORMAT, "manifest": manifest or {}}]
    lines += [{"t": "event", **e.model_dump(mode="json")} for e in journal.events]
    lines += [{"t": "effect", **e.model_dump(mode="json")} for e in journal.effects.values()]
    return "\n".join(json.dumps(line, sort_keys=True) for line in lines) + "\n"


def load_cassette(text: str | Iterable[str]) -> tuple[JournalSnapshot, dict[str, Any]]:
    rows = text.splitlines() if isinstance(text, str) else text
    journal = JournalSnapshot()
    manifest: dict[str, Any] = {}
    for raw in rows:
        if not raw.strip():
            continue
        row = json.loads(raw)
        kind = row.pop("t")
        if kind == "header":
            if row.get("format") != FORMAT:
                raise ValueError(f"unsupported cassette format: {row.get('format')}")
            manifest = row.get("manifest", {})
        elif kind == "event":
            journal.events.append(Event.model_validate(row))
        elif kind == "effect":
            rec = EffectRecord.model_validate(row)
            journal.effects[rec.key] = rec
    return journal, manifest


async def store_from_cassette(text: str, episode_id: str) -> MemoryJournalStore:
    """A store preloaded with the cassette. Open an EpisodeCtx on it with replay_only=True
    for strict replay, or normally for `agent_live` style continuation."""
    journal, _ = load_cassette(text)
    store = MemoryJournalStore()
    await store.append(episode_id, 0, events=journal.events, effects=list(journal.effects.values()))
    return store
