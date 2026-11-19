"""The mock world. See docs/plan/03-hard-cores.md section 2."""

from .canary import CanaryHit, detect, plant
from .state import (
    PatchConflict,
    WorldState,
    WorldView,
    diff_from_patches,
    field_changes,
    invert,
    naive_diff,
)
from .tools import (
    NeedsLLM,
    ToolHandler,
    ToolOutcome,
    apply_fault,
    assert_pure,
    pick_fault,
    resolve_handler,
    validate_args,
)
from .world import BuiltWorld, ToolResult, World, build_trajectory, build_world, fold_world

__all__ = [
    "BuiltWorld",
    "CanaryHit",
    "NeedsLLM",
    "PatchConflict",
    "ToolHandler",
    "ToolOutcome",
    "ToolResult",
    "World",
    "WorldState",
    "WorldView",
    "apply_fault",
    "assert_pure",
    "build_trajectory",
    "build_world",
    "detect",
    "diff_from_patches",
    "field_changes",
    "fold_world",
    "invert",
    "naive_diff",
    "pick_fault",
    "plant",
    "resolve_handler",
    "validate_args",
]
