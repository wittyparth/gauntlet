"""Embedding failure texts (CQ-R7): the offline `HashEmbedder` unless a gateway is given."""

from __future__ import annotations

import math
from collections.abc import Sequence

from gauntlet_core.llm.embed import HashEmbedder
from gauntlet_core.llm.gateway import Gateway

__all__ = ["BATCH", "EMBED_DIM", "embed_texts", "normalise"]

EMBED_DIM = 1536  # the `vector(N)` column is fixed at migration time
BATCH = 64


def normalise(v: Sequence[float], dim: int = EMBED_DIM) -> list[float]:
    """Cut or zero-pad to `dim`, then L2-normalise (so euclidean distance orders like cosine)."""
    out = list(v[:dim]) + [0.0] * max(0, dim - len(v))
    n = math.sqrt(sum(x * x for x in out))
    return [x / n for x in out] if n else out


async def embed_texts(
    texts: Sequence[str], gateway: Gateway | None = None, *, dim: int = EMBED_DIM
) -> list[list[float]]:
    """No gateway means `HashEmbedder(dim)`: deterministic, free, no network."""
    if gateway is None:
        h = HashEmbedder(dim)
        return [normalise(h.embed_one(t), dim) for t in texts]
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        batch = list(texts[i : i + BATCH])
        out.extend(normalise(v, dim) for v in await gateway.embed("embedder", batch))
    return out
