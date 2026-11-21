"""policies and policy_proposals (P4-1)

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE policies (
            id text NOT NULL,
            version integer NOT NULL,
            workspace_id text NOT NULL REFERENCES workspaces(id),
            name text NOT NULL,
            agent_id text REFERENCES agents(id),
            doc jsonb NOT NULL,
            status text NOT NULL,
            source_text text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_policies PRIMARY KEY (id, version),
            CONSTRAINT ck_policies_status CHECK (status IN ('draft','published'))
        )"""
    )
    op.execute("CREATE INDEX ix_policies_ws ON policies (workspace_id, id)")
    op.execute(
        """CREATE TABLE policy_proposals (
            id text PRIMARY KEY,
            workspace_id text NOT NULL REFERENCES workspaces(id),
            policy_id text NOT NULL,
            version integer NOT NULL,
            doc jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_policy_proposals_policy_id UNIQUE (policy_id, version)
        )"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE policy_proposals")
    op.execute("DROP TABLE policies")
