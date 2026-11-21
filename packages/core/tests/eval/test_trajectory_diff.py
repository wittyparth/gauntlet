from datetime import UTC, datetime

from check_helpers import scenario
from gauntlet_core.eval.trajectory_diff import diff_trajectories
from gauntlet_core.schema import (
    Event,
    FieldChange,
    RecordChange,
    StateDiff,
    Trajectory,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def ev(seq, kind, actor, **payload):
    return Event(seq=seq, kind=kind, actor=actor, sim_time=T0, payload=payload)


def traj(steps, diff=None):
    """steps: ("u", text) | ("a", text) | ("t", tool, args)"""
    events, cid = [], 0
    for s in steps:
        if s[0] == "u":
            events.append(ev(len(events), "user_message", "user", text=s[1]))
        elif s[0] == "a":
            events.append(ev(len(events), "agent_message", "agent", text=s[1]))
        else:
            cid += 1
            events.append(
                ev(len(events), "tool_call", "agent", call_id=f"c{cid}", tool=s[1], args=s[2])
            )
            events.append(
                ev(len(events), "tool_result", "tool", call_id=f"c{cid}", ok=True, result={"x": 1})
            )
    return Trajectory(episode_id="e", scenario=scenario(), events=events, diff=diff or StateDiff())


BASE = [
    ("u", "I want a refund for order 1001"),
    ("t", "get_order", {"id": "1001"}),
    ("a", "Your order is eligible, shall I proceed?"),
    ("u", "yes please"),
    ("t", "refund", {"id": "1001", "amount": 20}),
    ("a", "Refund issued."),
]


def test_identical_gives_all_same():
    d = diff_trajectories(traj(BASE), traj(BASE))
    assert [r.status for r in d.rows] == ["same"] * 6
    assert d.first_divergence is None and not d.truncated


def test_inserted_tool_call_is_only_b():
    other = [*BASE[:2], ("t", "get_policy", {}), *BASE[2:]]
    d = diff_trajectories(traj(BASE), traj(other))
    assert [r.status for r in d.rows].count("only_b") == 1
    only_b = next(r for r in d.rows if r.status == "only_b")
    assert only_b.kind == "tool_call" and only_b.a_seq is None and only_b.b_seq is not None
    assert d.first_divergence == (None, only_b.b_seq)


def test_changed_args_is_changed():
    other = [*BASE[:4], ("t", "refund", {"id": "1001", "amount": 99}), BASE[5]]
    d = diff_trajectories(traj(BASE), traj(other))
    statuses = [r.status for r in d.rows]
    assert statuses.count("changed") == 1 and statuses.count("same") == 5
    row = next(r for r in d.rows if r.status == "changed")
    assert row.kind == "tool_call" and "99" in (row.summary_b or "")
    assert d.first_divergence == (row.a_seq, row.b_seq)


def test_reworded_message_aligns_as_changed_and_unrelated_does_not_align():
    other = [BASE[0], BASE[1], ("a", "Your order is eligible. Should I go ahead?"), *BASE[3:]]
    d = diff_trajectories(traj(BASE), traj(other))
    assert [r.status for r in d.rows].count("changed") == 1
    far = [BASE[0], BASE[1], ("a", "zzzz qqqq"), *BASE[3:]]
    d2 = diff_trajectories(traj(BASE), traj(far))
    assert sorted(r.status for r in d2.rows).count("only_a") == 1
    assert sorted(r.status for r in d2.rows).count("only_b") == 1


def test_reordered_messages_still_align():
    a = [("u", "hello there"), ("a", "hi, how can I help"), ("u", "refund please"), ("a", "done")]
    b = [("u", "hello there"), ("a", "hi, how can I help"), ("a", "one moment"),
         ("u", "refund please"), ("a", "done")]  # fmt: skip
    d = diff_trajectories(traj(a), traj(b))
    assert [r.status for r in d.rows].count("same") == 4
    assert [r.status for r in d.rows].count("only_b") == 1


def test_cap_sets_truncated():
    many = [("u", f"message number {i}") for i in range(250)]
    d = diff_trajectories(traj(many), traj(many))
    assert d.truncated and len(d.rows) == 200


def test_state_diff_comparison():
    ca = RecordChange(collection="orders", id="1001", kind="changed",
                      fields=[FieldChange(path="status", old="paid", new="refunded"),
                              FieldChange(path="note", old=None, new="a")], seqs=[3])  # fmt: skip
    cb = RecordChange(collection="orders", id="1001", kind="changed",
                      fields=[FieldChange(path="status", old="paid", new="cancelled"),
                              FieldChange(path="flag", old=None, new=True)], seqs=[3])  # fmt: skip
    d = diff_trajectories(traj([], StateDiff(changes=[ca])), traj([], StateDiff(changes=[cb])))
    assert [(k.collection, k.id, k.path) for k in d.state_diff.differing] == [
        ("orders", "1001", "status")
    ]
    assert [k.path for k in d.state_diff.only_a] == ["note"]
    assert [k.path for k in d.state_diff.only_b] == ["flag"]
