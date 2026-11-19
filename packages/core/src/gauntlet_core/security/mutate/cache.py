"""JSONL cache for model-backed mutations, so reruns and CI are reproducible and free."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

__all__ = ["MutationCache", "cache_key", "gateway_model"]


def gateway_model(gateway: Any, role: str = "generator") -> str:
    """Best-effort model id for the cache key (falls back to the gateway's class name)."""
    try:
        return str(gateway.config.llm.roles[role].model)
    except (AttributeError, KeyError):
        return type(gateway).__name__


def cache_key(op: str, lang: str, payload: str, model: str) -> str:
    return hashlib.sha256(json.dumps([op, lang, payload, model]).encode()).hexdigest()


class MutationCache:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._data: dict[str, str] = {}
        if path is not None and path.is_file():
            for line in path.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._data[row["key"]] = row["text"]

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def put(self, key: str, text: str) -> None:
        self._data[key] = text
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(json.dumps({"key": key, "text": text}, ensure_ascii=False) + "\n")
