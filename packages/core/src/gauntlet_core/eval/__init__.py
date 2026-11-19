"""Evaluation outputs: rubric library, scoring and run reports (judges live in `judges/`)."""

from .report import (
    Caution,
    DimensionStats,
    EpisodeRecord,
    FailureRef,
    RunReport,
    ScenarioStats,
    aggregate_run,
)
from .rubrics import RULE_STAGE, load_rubrics, rule_context
from .scoring import SEVERITY_WEIGHT, composite_score, dimension_score

__all__ = [
    "RULE_STAGE",
    "SEVERITY_WEIGHT",
    "Caution",
    "DimensionStats",
    "EpisodeRecord",
    "FailureRef",
    "RunReport",
    "ScenarioStats",
    "aggregate_run",
    "composite_score",
    "dimension_score",
    "load_rubrics",
    "rule_context",
]
