"""The check language evaluators (L5): final-trajectory and prefix evaluation (contracts 4).

The AST lives in `gauntlet_core.schema.checks`. Importing this package registers all nodes.
"""

from . import calls, logic, text, worldnodes  # noqa: F401  (register node types)
from .context import PrefixView, ProposedAction
from .detectors import DetectorFn, get, names, register, text_detector
from .evaluate import (
    NotPrefixEvaluable,
    assert_prefix_evaluable,
    evaluate_final,
    evaluate_prefix,
    is_prefix_evaluable,
)
from .matchers import match_value, resolve_path
from .registry import NODES, register_node

__all__ = [
    "NODES",
    "DetectorFn",
    "NotPrefixEvaluable",
    "PrefixView",
    "ProposedAction",
    "assert_prefix_evaluable",
    "evaluate_final",
    "evaluate_prefix",
    "get",
    "is_prefix_evaluable",
    "match_value",
    "names",
    "register",
    "register_node",
    "resolve_path",
    "text_detector",
]
