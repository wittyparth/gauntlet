"""badge_tokens (P3-4)

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE badge_tokens (
            id text PRIMARY KEY,
            workspace_id text NOT NULL REFERENCES workspaces(id),
            agent_id text NOT NULL REFERENCES agents(id),
            token text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            revoked_at timestamptz,
            CONSTRAINT uq_badge_tokens_token UNIQUE (token)
        )"""
    )
    op.execute("CREATE INDEX ix_badge_tokens_agent ON badge_tokens (agent_id)")


def downgrade() -> None:
    op.execute("DROP TABLE badge_tokens")
