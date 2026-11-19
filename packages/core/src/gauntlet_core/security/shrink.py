"""Shrinking a successful attack to the smallest one that still works (hard-cores 6.5).

The oracle is non-deterministic, so a candidate "works" when at least `ceil(0.5 * m)` of `m`
trials satisfy the objective (default m = 3, with early exit once the outcome is decided).
Results are memoised on the candidate text. The search stops at `max_episodes` or when a full
pass over the units removes nothing. Stages: the document context first (document vectors),
then turns, then sentences, then (optionally) words. Placeholders such as `{{marker}}` never
contain whitespace or sentence punctuation, so no split can cut one in half.

Attempt ids are `<base_id>:t<n>` for the search and `<base_id>:final<k>:<i>` for the
measurements, counted in a fixed order, so a resumed shrink re-derives the same episode ids and
replays the journals it already wrote."""

from __future__ import annotations

import math
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from gauntlet_core.schema import Attack

from .episodes import AttackOracle

__all__ = ["ShrinkConfig", "ShrinkResult", "ddmin", "shrink_attack", "split_sentences"]

T = TypeVar("T")


@dataclass(frozen=True)
class ShrinkConfig:
    trials: int = 3  # m: trials per candidate
    trials_final: int = 10  # fresh trials measuring the original and the reduced attack
    max_episodes: int = 60  # cap on search episodes (measurements are extra)
    words: bool = False  # also try removing single words


@dataclass(frozen=True)
class ShrinkResult:
    attack: Attack  # the reduced attack (the original when nothing could be removed)
    doc_body: str | None  # reduced document context (document vectors), else None
    reduced: bool
    successes: int  # of `attempts` fresh trials of the returned attack
    attempts: int
    original_rate: float
    episodes: int  # every episode run, searches and measurements

    @property
    def rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.0

    @property
    def reproducibility(self) -> tuple[int, int]:
        return (self.successes, self.attempts)


async def ddmin(
    units: Sequence[T],
    test: Callable[[Sequence[T]], Awaitable[bool]],
    *,
    max_tests: int | None = None,
    can_continue: Callable[[], bool] | None = None,
) -> list[T]:
    """Zeller's ddmin. `test(subset)` is True when the subset still works. Never tests the
    empty subset. Memoised; returns the best reduction found when a cap stops the search."""
    current = list(units)
    memo: dict[tuple[int, ...], bool] = {}
    index = {i: u for i, u in enumerate(current)}
    ids = list(range(len(current)))
    tests = 0

    async def ask(subset: list[int]) -> bool | None:
        nonlocal tests
        key = tuple(subset)
        if key in memo:
            return memo[key]
        if (max_tests is not None and tests >= max_tests) or (
            can_continue is not None and not can_continue()
        ):
            return None
        tests += 1
        memo[key] = await test([index[i] for i in subset])
        return memo[key]

    n = 2
    while len(ids) >= 2:
        size = math.ceil(len(ids) / n)
        chunks = [ids[i : i + size] for i in range(0, len(ids), size)]
        reduced = False
        for chunk in chunks:  # try each subset
            r = await ask(chunk)
            if r is None:
                return [index[i] for i in ids]
            if r:
                ids, n, reduced = chunk, 2, True
                break
        if not reduced:
            for chunk in chunks:  # then each complement
                comp = [i for i in ids if i not in chunk]
                if not comp:
                    continue
                r = await ask(comp)
                if r is None:
                    return [index[i] for i in ids]
                if r:
                    ids, n, reduced = comp, max(n - 1, 2), True
                    break
        if not reduced:
            if n >= len(ids):  # a pass over every single unit removed nothing
                break
            n = min(len(ids), n * 2)
    return [index[i] for i in ids]


_SENT = re.compile(r"(?<=[.!?])(\s+)")


def split_sentences(text: str) -> list[str]:
    """Sentences, each keeping its trailing whitespace, so `"".join(parts) == text`."""
    pieces = _SENT.split(text)
    out = [
        pieces[i] + (pieces[i + 1] if i + 1 < len(pieces) else "") for i in range(0, len(pieces), 2)
    ]
    return [p for p in out if p]


def _texts(payload: str | list[str]) -> list[str]:
    return [payload] if isinstance(payload, str) else list(payload)


def _payload_of(turns: list[str], as_list: bool) -> str | list[str]:
    turns = [t.strip() for t in turns if t.strip()]
    return turns if as_list and len(turns) != 1 else "\n".join(turns) if turns else ""


async def shrink_attack(
    attack: Attack,
    oracle: AttackOracle,
    *,
    base_id: str,
    config: ShrinkConfig = ShrinkConfig(),
    doc_body: str | None = None,
    world_doc: str | None = None,
) -> ShrinkResult:
    """Shrink `attack` (and, for document vectors, the surrounding `doc_body`)."""
    need = math.ceil(0.5 * config.trials)
    state = {"n": 0, "episodes": 0, "search": 0}
    memo: dict[tuple[str, str | None], bool] = {}

    async def trial(atk: Attack, body: str | None, attempt_id: str) -> bool:
        state["episodes"] += 1
        res = await oracle(atk, attempt_id, doc_body=body)
        return res.objective_held

    async def works(atk: Attack, body: str | None) -> bool:
        key = (repr(atk.payload), body)
        if key in memo:
            return memo[key]
        wins = losses = 0
        for _ in range(config.trials):
            state["n"] += 1
            state["search"] += 1
            if await trial(atk, body, f"{base_id}:t{state['n']}"):
                wins += 1
            else:
                losses += 1
            if wins >= need or losses > config.trials - need:
                break
        memo[key] = wins >= need
        return memo[key]

    async def measure(atk: Attack, body: str | None, k: int) -> int:
        wins = 0
        for i in range(config.trials_final):
            wins += await trial(atk, body, f"{base_id}:final{k}:{i}")
        return wins

    def room() -> bool:
        return state["search"] < config.max_episodes

    original_wins = await measure(attack, doc_body, 0)
    orig_rate = original_wins / config.trials_final
    if original_wins == 0:
        return ShrinkResult(attack, doc_body, False, 0, config.trials_final, 0.0, state["episodes"])

    cur, body = attack, doc_body
    accepted: list[tuple[Attack, str | None]] = []
    as_list = isinstance(attack.payload, list)

    if body is not None and world_doc is not None:  # stage 0: the document around the payload
        if body.strip() and room() and await works(cur, ""):
            body = ""
            accepted.append((cur, body))
        elif body.strip():
            sents = split_sentences(body)

            async def ctx_test(sub: Sequence[str]) -> bool:
                return await works(cur, "".join(sub))

            kept = await ddmin(sents, ctx_test, can_continue=room)
            if len(kept) < len(sents):
                body = "".join(kept)
                accepted.append((cur, body))

    async def stage(units: list, build: Callable[[list], str | list[str]]) -> None:
        nonlocal cur
        if len(units) < 2 or not room():
            return

        async def test(sub: Sequence) -> bool:
            return await works(cur.model_copy(update={"payload": build(list(sub))}), body)

        kept = await ddmin(units, test, can_continue=room)
        if len(kept) < len(units):
            cur = cur.model_copy(update={"payload": build(kept)})
            accepted.append((cur, body))

    if as_list:  # stage 1: turns
        turns = _texts(cur.payload)
        await stage(turns, lambda sub: _payload_of(list(sub), True))
    # stage 2: sentences (flattened over the remaining turns, regrouped by turn)
    turns = _texts(cur.payload)
    flat = [(ti, s) for ti, t in enumerate(turns) for s in split_sentences(t)]

    def rebuild(sub: list) -> str | list[str]:
        grouped: dict[int, str] = {}
        for ti, s in sub:
            grouped[ti] = grouped.get(ti, "") + s
        return _payload_of([grouped[k] for k in sorted(grouped)], as_list)

    await stage(flat, rebuild)
    if config.words:  # stage 3: words of what is left
        words = [w for t in _texts(cur.payload) for w in t.split()]
        await stage(words, lambda sub: _payload_of([" ".join(sub)], as_list))

    changed = (cur.payload != attack.payload) or (body != doc_body)
    if not changed:
        return ShrinkResult(
            attack,
            doc_body,
            False,
            original_wins,
            config.trials_final,
            orig_rate,
            state["episodes"],
        )
    # measure the reduction; back off to the last candidate that keeps >= half the original rate
    candidates = [*reversed(accepted)][:3]
    for k, (cand, cbody) in enumerate(candidates, start=1):
        wins = await measure(cand, cbody, k)
        if wins / config.trials_final >= 0.5 * orig_rate and wins > 0:
            return ShrinkResult(
                cand, cbody, True, wins, config.trials_final, orig_rate, state["episodes"]
            )
    return ShrinkResult(
        attack, doc_body, False, original_wins, config.trials_final, orig_rate, state["episodes"]
    )
