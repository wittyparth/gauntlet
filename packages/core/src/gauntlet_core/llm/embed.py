"""Deterministic offline embeddings: hashed character 3-grams, signed, L2-normalised."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence


class HashEmbedder:
    def __init__(self, dim: int = 256) -> None:
        if dim < 8:
            raise ValueError("dim must be at least 8")
        self.dim = dim

    def embed_one(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        t = f"  {text.lower()}  "
        for i in range(len(t) - 2):
            h = hashlib.blake2b(t[i : i + 3].encode(), digest_size=8).digest()
            n = int.from_bytes(h, "big")
            v[n % self.dim] += 1.0 if (n >> 63) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in v))
        return [x / norm for x in v] if norm else v

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if not na or not nb:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)
