"""World state, patches and diffs (docs/plan/03-hard-cores.md sections 2.1 and 2.2).

State is never stored: it is the fold of an initial snapshot and the patches carried by
tool_result events. Records are treated as immutable values.
"""

from __future__ import annotations

import copy
from typing import Any

from gauntlet_core.schema import (
    FieldChange,
    Json,
    PatchOp,
    RecordChange,
    StateDiff,
    WorldSnapshot,
)

_MISSING: Any = object()


class PatchConflict(Exception):
    """A patch does not apply to the current state. Always a platform bug."""


class WorldState:
    def __init__(self, data: dict[str, dict[str, Json]] | None = None) -> None:
        self._data: dict[str, dict[str, Json]] = data or {}
        self._owned: set[str] = set()  # collections copied since the last snapshot

    @classmethod
    def from_seed(cls, seed: dict[str, list[Json]]) -> WorldState:
        data: dict[str, dict[str, Json]] = {}
        for collection, records in seed.items():
            data[collection] = {}
            for rec in records:
                if "id" not in rec:
                    raise ValueError(f"seed record in '{collection}' has no 'id': {rec}")
                data[collection][str(rec["id"])] = copy.deepcopy(rec)
        return cls(data)

    @classmethod
    def from_snapshot(cls, snapshot: WorldSnapshot) -> WorldState:
        return cls(dict(snapshot))  # collections are shared until first write

    def snapshot(self) -> WorldSnapshot:
        """O(collections). The snapshot is unaffected by later writes (copy-on-write)."""
        self._owned.clear()
        return dict(self._data)

    def get(self, collection: str, id: str) -> Json | None:
        return self._data.get(collection, {}).get(id)

    def list(self, collection: str, **eq: Any) -> list[Json]:
        return [
            r
            for r in self._data.get(collection, {}).values()
            if all(r.get(k) == v for k, v in eq.items())
        ]

    def size(self, collection: str) -> int:
        return len(self._data.get(collection, {}))

    def _writable(self, collection: str) -> dict[str, Json]:
        if collection not in self._owned:
            self._data[collection] = dict(self._data.get(collection, {}))
            self._owned.add(collection)
        return self._data[collection]

    def check(self, patch: list[PatchOp]) -> None:
        """Raise PatchConflict if `patch` would not apply cleanly. Does not mutate."""
        shadow: dict[tuple[str, str], Json | None] = {}
        for op in patch:
            key = (op.collection, op.id)
            cur = shadow[key] if key in shadow else self.get(op.collection, op.id)
            if op.op == "add":
                if cur is not None:
                    raise PatchConflict(f"add: {key} already exists")
                if op.value is None:
                    raise PatchConflict(f"add: {key} has no value")
                shadow[key] = op.value
            else:
                if cur is None:
                    raise PatchConflict(f"{op.op}: {key} does not exist")
                if op.before is not None and op.before != cur:
                    raise PatchConflict(f"{op.op}: {key} `before` does not match current state")
                if op.op == "replace" and op.value is None:
                    raise PatchConflict(f"replace: {key} has no value")
                shadow[key] = op.value if op.op == "replace" else None

    def apply(self, patch: list[PatchOp]) -> None:
        self.check(patch)
        for op in patch:
            col = self._writable(op.collection)
            if op.op == "remove":
                del col[op.id]
            else:
                col[op.id] = copy.deepcopy(op.value)  # type: ignore[assignment]


class WorldView:
    """Read-only view handed to tool handlers."""

    def __init__(self, state: WorldState) -> None:
        self._s = state

    def get(self, collection: str, id: str) -> Json | None:
        rec = self._s.get(collection, id)
        return copy.deepcopy(rec) if rec is not None else None

    def list(self, collection: str, **eq: Any) -> list[Json]:
        return copy.deepcopy(self._s.list(collection, **eq))

    def size(self, collection: str) -> int:
        return self._s.size(collection)


def invert(patch: list[PatchOp]) -> list[PatchOp]:
    """The patch that undoes `patch`. Requires `before` on replace and remove ops."""
    out: list[PatchOp] = []
    for op in reversed(patch):
        if op.op == "add":
            out.append(PatchOp(op="remove", collection=op.collection, id=op.id, before=op.value))
        elif op.op == "remove":
            if op.before is None:
                raise ValueError("cannot invert a remove without `before`")
            out.append(PatchOp(op="add", collection=op.collection, id=op.id, value=op.before))
        else:
            if op.before is None:
                raise ValueError("cannot invert a replace without `before`")
            out.append(
                PatchOp(
                    op="replace",
                    collection=op.collection,
                    id=op.id,
                    value=op.before,
                    before=op.value,
                )
            )
    return out


def field_changes(old: Any, new: Any, prefix: str = "") -> list[FieldChange]:
    """Dotted-path differences between two JSON values. Lists are reported whole."""
    if isinstance(old, dict) and isinstance(new, dict):
        out: list[FieldChange] = []
        for k in sorted(set(old) | set(new)):
            path = f"{prefix}.{k}" if prefix else str(k)
            a, b = old.get(k, _MISSING), new.get(k, _MISSING)
            if a is _MISSING:
                out.append(FieldChange(path=path, old=None, new=b))
            elif b is _MISSING:
                out.append(FieldChange(path=path, old=a, new=None))
            else:
                out.extend(field_changes(a, b, path))
        return out
    return [] if old == new else [FieldChange(path=prefix, old=old, new=new)]


def _change(collection: str, id: str, old: Json | None, new: Json | None, seqs: list[int]):
    if (old is None and new is None) or old == new:
        return None
    if old is None:
        return RecordChange(collection=collection, id=id, kind="added", record=new, seqs=seqs)
    if new is None:
        return RecordChange(collection=collection, id=id, kind="removed", record=old, seqs=seqs)
    return RecordChange(
        collection=collection, id=id, kind="changed", fields=field_changes(old, new), seqs=seqs
    )


def diff_from_patches(
    initial: WorldSnapshot, patches: list[tuple[int, list[PatchOp]]]
) -> StateDiff:
    """Net change from `initial` after applying `patches` in order.

    Each patch comes with the seq of the tool_result event that carried it, so every change
    names the events that caused it. Changes that cancel out (add then remove, replace back
    to the original) disappear.
    """
    original: dict[tuple[str, str], Json | None] = {}
    current: dict[tuple[str, str], Json | None] = {}
    seqs: dict[tuple[str, str], list[int]] = {}
    for seq, patch in patches:
        for op in patch:
            key = (op.collection, op.id)
            if key not in original:
                original[key] = initial.get(op.collection, {}).get(op.id)
            current[key] = None if op.op == "remove" else op.value
            if seq not in seqs.setdefault(key, []):
                seqs[key].append(seq)
    changes = [
        c
        for key in sorted(original)
        if (c := _change(key[0], key[1], original[key], current[key], seqs[key])) is not None
    ]
    return StateDiff(changes=changes)


def naive_diff(a: WorldSnapshot, b: WorldSnapshot) -> StateDiff:
    """Deep comparison of two snapshots, without causal seqs. Cross-checks diff_from_patches."""
    changes = []
    for collection in sorted(set(a) | set(b)):
        ra, rb = a.get(collection, {}), b.get(collection, {})
        for id in sorted(set(ra) | set(rb)):
            c = _change(collection, id, ra.get(id), rb.get(id), [])
            if c is not None:
                changes.append(c)
    return StateDiff(changes=changes)
