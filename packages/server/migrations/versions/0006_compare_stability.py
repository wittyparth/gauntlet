"""episodes.latency_ms, tokens_in, tokens_out (P3-1), backfilled from the journal

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATEMENTS = [
    "ALTER TABLE episodes ADD COLUMN latency_ms int",
    "ALTER TABLE episodes ADD COLUMN tokens_in int",
    "ALTER TABLE episodes ADD COLUMN tokens_out int",
    # agent-side time only: agent messages and tool results, never the simulator
    """UPDATE episodes e SET latency_ms = coalesce((
        SELECT sum((doc->>'wall_ms')::int) FROM events
        WHERE episode_id = e.id AND kind IN ('agent_message', 'tool_result')), 0)
       WHERE e.status = 'done'""",
    """UPDATE episodes e SET
        tokens_in = coalesce((SELECT sum((cost->>'input_tokens')::int) FROM effects
                              WHERE episode_id = e.id AND status = 'done'), 0),
        tokens_out = coalesce((SELECT sum((cost->>'output_tokens')::int) FROM effects
                               WHERE episode_id = e.id AND status = 'done'), 0)
       WHERE e.status = 'done'""",
]


def upgrade() -> None:
    for stmt in _STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for col in ("tokens_out", "tokens_in", "latency_ms"):
        op.execute(f"ALTER TABLE episodes DROP COLUMN {col}")
