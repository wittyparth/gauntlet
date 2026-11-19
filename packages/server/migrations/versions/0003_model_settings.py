"""workspace_settings and runs.role_settings: per-workspace model choices per role

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_settings",
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column(
            "model_roles",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_workspace_settings_workspace_id_workspaces",
        ),
        sa.PrimaryKeyConstraint("workspace_id", name="pk_workspace_settings"),
    )
    op.add_column("runs", sa.Column("role_settings", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "role_settings")
    op.drop_table("workspace_settings")
