"""effects.span: nested effect spans (hard-cores 1.7a)

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("effects", "effects_archive"):
        op.add_column(table, sa.Column("span", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    for table in ("effects_archive", "effects"):
        op.drop_column(table, "span")
