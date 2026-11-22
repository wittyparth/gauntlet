"""Failure mining over production conversations (P5-2): scoring, anonymisation, conversion."""

from .anonymise import Anonymised, Residual, anonymise, residual_scan
from .score import DetectorSpec, FailureScore, SampledJudge, score_conversation
from .to_scenario import ConversionFailed, MinedDraft, ScenarioDraft, to_scenario
from .world_from_trace import world_from_trace

__all__ = [
    "Anonymised",
    "ConversionFailed",
    "DetectorSpec",
    "FailureScore",
    "MinedDraft",
    "Residual",
    "SampledJudge",
    "ScenarioDraft",
    "anonymise",
    "residual_scan",
    "score_conversation",
    "to_scenario",
    "world_from_trace",
]
