"""Failure clustering and root-cause attribution (P3-6)."""

from .attribute import (
    ROOT_CAUSES,
    Attribution,
    RootCause,
    attribute_by_rules,
    attribute_episode,
    cluster_root_cause,
    hint_for,
)
from .embed import EMBED_DIM, embed_texts, normalise
from .group import cluster_vectors, group_failures
from .name import ClusterName, Exemplar, MemoryNameCache, name_cluster
from .text import failed_check_ids, failure_text

__all__ = [
    "EMBED_DIM",
    "ROOT_CAUSES",
    "Attribution",
    "ClusterName",
    "Exemplar",
    "MemoryNameCache",
    "RootCause",
    "attribute_by_rules",
    "attribute_episode",
    "cluster_root_cause",
    "cluster_vectors",
    "embed_texts",
    "failed_check_ids",
    "failure_text",
    "group_failures",
    "hint_for",
    "name_cluster",
    "normalise",
]
