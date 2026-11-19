"""Statistics for suite results (L4). Pure functions, deterministic given a seed.

Imports only the standard library.
"""

from .agreement import Agreement, cohens_kappa, judge_agreement
from .compare import (
    Comparison,
    Flip,
    classify_flip,
    compare_runs,
    fisher_exact,
    flip_table,
    sign_flip_pvalue,
)
from .intervals import Estimate, wilson_estimate, wilson_interval
from .passk import (
    ReliabilityPoint,
    pass_hat_k,
    reliability_curve,
    suite_pass_hat_k,
    suite_pass_rate,
)
from .sequential import SequentialDecision, beta_cdf, posterior_mean, sequential_decision

__all__ = [
    "Agreement",
    "Comparison",
    "Estimate",
    "Flip",
    "ReliabilityPoint",
    "SequentialDecision",
    "beta_cdf",
    "classify_flip",
    "cohens_kappa",
    "compare_runs",
    "fisher_exact",
    "flip_table",
    "judge_agreement",
    "pass_hat_k",
    "posterior_mean",
    "reliability_curve",
    "sequential_decision",
    "sign_flip_pvalue",
    "suite_pass_hat_k",
    "suite_pass_rate",
    "wilson_estimate",
    "wilson_interval",
]
