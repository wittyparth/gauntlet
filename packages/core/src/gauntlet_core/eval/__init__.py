"""Evaluation outputs: rubric library, scoring and run reports (judges live in `judges/`)."""

from .compare import CompareReport, RunData, compare_runs, comparison_seed
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
from .trajectory_diff import TrajectoryDiff, diff_trajectories

__all__ = [
    "RULE_STAGE",
    "SEVERITY_WEIGHT",
    "Caution",
    "CompareReport",
    "DimensionStats",
    "EpisodeRecord",
    "FailureRef",
    "RunData",
    "RunReport",
    "ScenarioStats",
    "TrajectoryDiff",
    "aggregate_run",
    "compare_runs",
    "comparison_seed",
    "composite_score",
    "diff_trajectories",
    "dimension_score",
    "load_rubrics",
    "rule_context",
]
