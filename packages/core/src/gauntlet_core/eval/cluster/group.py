"""Grouping failure vectors (P3-6). Needs scikit-learn (`gauntlet-core[cluster]`)."""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from typing import Any

__all__ = ["MIN_FOR_HDBSCAN", "cluster_vectors", "group_failures"]

MIN_FOR_HDBSCAN = 6


def cluster_vectors(vectors: Any, *, min_cluster_size: int = 3, min_samples: int = 2) -> list[int]:
    """HDBSCAN (euclidean, eom) on L2-normalised rows, which orders like cosine. One label per
    row, `-1` is noise. Deterministic for fixed vectors."""
    import numpy as np
    from sklearn.cluster import HDBSCAN

    x = np.asarray(vectors, dtype=float)
    if x.ndim != 2 or len(x) == 0:
        return []
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    x = x / np.where(norms == 0, 1.0, norms)
    with warnings.catch_warnings():  # sklearn announces a default change for `copy`
        warnings.simplefilter("ignore", FutureWarning)
        labels = HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            metric="euclidean",
            cluster_selection_method="eom",
        ).fit_predict(x)
    return [int(v) for v in labels]


def group_failures(
    vectors: Any, check_ids: Sequence[Sequence[str]], *, min_cluster_size: int = 3
) -> list[int]:
    """With fewer than 6 failures HDBSCAN has nothing to work with: group by identical sorted
    tuples of failed check ids instead (labels in order of first appearance, no noise)."""
    n = len(check_ids)
    if n < MIN_FOR_HDBSCAN:
        seen: dict[tuple[str, ...], int] = {}
        return [seen.setdefault(tuple(sorted(c)), len(seen)) for c in check_ids]
    return cluster_vectors(vectors, min_cluster_size=min_cluster_size)
