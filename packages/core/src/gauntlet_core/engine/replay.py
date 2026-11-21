"""Preparing an `agent_live` replay episode (hard-cores 1.6a).

`fork_for_agent_live` copies a recorded journal into a new episode, minus everything the new
agent version must do live: `target` effects and every effect nested inside them (1.7a). What
stays are the *top-level* effects (the simulator's model calls, the judges) tagged as
recordings, and every event, which the ctx verifies positionally while the replay stays in
sync.
"""

from __future__ import annotations

from gauntlet_core.schema import EffectRecord

from .store import JournalStore

__all__ = ["RECORDED", "fork_for_agent_live", "is_recorded"]

RECORDED = "recorded"  # marker in `EffectRecord.span` for a copied top-level effect


def is_recorded(rec: EffectRecord) -> bool:
    return bool(rec.span and rec.span.get(RECORDED))


def _ordinal(key: str) -> int:
    return int(key.partition(":")[2])


def nested_keys(effects: dict[str, EffectRecord]) -> set[str]:
    """Keys of effects that ran inside a `target` effect, from the targets' spans.

    A span says how many effects of each kind started inside, not where the range starts. In
    the episode loop the simulator's `llm` effect precedes every target call, so n + 1
    top-level `llm` effects come before target n (when the simulator uses `llm` effects at all).
    """
    targets = sorted((_ordinal(k), r) for k, r in effects.items() if r.kind == "target")
    top_llm = sum(1 for r in effects.values() if r.kind == "llm" and not is_recorded(r))
    inside = {k: 0 for k in ("llm", "tool", "rng")}
    nested_llm_total = sum(
        int((r.span or {}).get("ordinals", {}).get("llm", 0)) for _, r in targets
    )
    sim_uses_llm = top_llm - nested_llm_total >= len(targets)
    out: set[str] = set()
    for n, rec in targets:
        for kind, count in ((rec.span or {}).get("ordinals") or {}).items():
            before = (n + 1 if kind == "llm" and sim_uses_llm else 0) + inside.get(kind, 0)
            out.update(f"{kind}:{i}" for i in range(before, before + int(count)))
            inside[kind] = inside.get(kind, 0) + int(count)
    return out


async def fork_for_agent_live(store: JournalStore, source_id: str, new_id: str) -> None:
    """Copy `source_id`'s journal into `new_id` (epoch 0; the caller created the episode).

    Kept: all events, and every finished top-level non-target effect, tagged as recorded and
    with its cost cleared (replayed effects cost nothing). Dropped: pending records, `target`
    effects and everything nested in them."""
    snap = await store.load(source_id)
    nested = nested_keys(snap.effects)
    kept = [
        rec.model_copy(update={"span": {RECORDED: True}, "cost": None})
        for key, rec in snap.effects.items()
        if rec.kind != "target"
        and rec.status in ("done", "failed")
        and (key not in nested or is_recorded(rec))
    ]
    await store.append(new_id, 0, events=snap.events, effects=kept)
