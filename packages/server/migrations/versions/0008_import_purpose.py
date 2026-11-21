"""runs.purpose accepts 'import' (cassette imports, P3-3)

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE runs DROP CONSTRAINT ck_runs_purpose")
    op.execute(
        "ALTER TABLE runs ADD CONSTRAINT ck_runs_purpose "
        "CHECK (purpose IN ('eval','campaign','replay','verify','import'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE runs DROP CONSTRAINT ck_runs_purpose")
    op.execute(
        "ALTER TABLE runs ADD CONSTRAINT ck_runs_purpose "
        "CHECK (purpose IN ('eval','campaign','replay','verify'))"
    )
