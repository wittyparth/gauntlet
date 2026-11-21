"""runs.adaptive, scenarios.quarantined / quarantine_reason / quarantined_at (P3-2)

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = [
    "ALTER TABLE runs ADD COLUMN adaptive boolean NOT NULL DEFAULT false",
    "ALTER TABLE scenarios ADD COLUMN quarantined boolean NOT NULL DEFAULT false",
    "ALTER TABLE scenarios ADD COLUMN quarantine_reason text",
    "ALTER TABLE scenarios ADD COLUMN quarantined_at timestamptz",
]


def upgrade() -> None:
    for stmt in _UP:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("ALTER TABLE scenarios DROP COLUMN quarantined_at")
    op.execute("ALTER TABLE scenarios DROP COLUMN quarantine_reason")
    op.execute("ALTER TABLE scenarios DROP COLUMN quarantined")
    op.execute("ALTER TABLE runs DROP COLUMN adaptive")
