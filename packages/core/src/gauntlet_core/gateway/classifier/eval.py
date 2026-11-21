"""Measure a classifier on labelled texts (P4-4): TPR at 1 percent FPR and AUC."""

from __future__ import annotations

from collections.abc import Sequence

from .model import InjectionClassifier

__all__ = ["evaluate_classifier"]


def _auc(pos: Sequence[float], neg: Sequence[float]) -> float:
    """P(score(pos) > score(neg)), ties count half (Mann-Whitney)."""
    if not pos or not neg:
        return float("nan")
    wins = 0.0
    for p in pos:
        for n in neg:
            wins += 1.0 if p > n else 0.5 if p == n else 0.0
    return wins / (len(pos) * len(neg))


def evaluate_classifier(
    classifier: InjectionClassifier,
    positives: Sequence[str],
    negatives: Sequence[str],
    *,
    batch: int = 16,
) -> dict[str, float | int]:
    def run(texts: Sequence[str]) -> list[float]:
        out: list[float] = []
        for i in range(0, len(texts), batch):
            out += classifier.score(list(texts[i : i + batch]))
        return out

    pos, neg = run(positives), run(negatives)
    # The smallest threshold whose false-positive rate on the negatives is at most 1 percent.
    allowed = int(len(neg) * 0.01)
    ranked = sorted(neg, reverse=True)
    threshold = ranked[allowed] + 1e-12 if neg and allowed < len(ranked) else 0.0
    tpr = sum(1 for p in pos if p >= threshold) / len(pos) if pos else float("nan")
    return {
        "tpr_at_fpr_1pct": tpr,
        "auc": _auc(pos, neg),
        "threshold_at_fpr_1pct": threshold,
        "n_pos": len(pos),
        "n_neg": len(neg),
    }
