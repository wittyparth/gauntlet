"""evidence_packs (P5-7)

Revision ID: 0018
Revises: 0017
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE evidence_packs (
            id text PRIMARY KEY,
            workspace_id text NOT NULL REFERENCES workspaces(id),
            agent_version_id text NOT NULL REFERENCES agent_versions(id),
            frameworks jsonb NOT NULL DEFAULT '[]'::jsonb,
            status text NOT NULL DEFAULT 'queued',
            object_key text,
            sha256 text,
            signed boolean NOT NULL DEFAULT false,
            error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz,
            CONSTRAINT ck_evidence_packs_status
                CHECK (status IN ('queued','running','done','failed'))
        )"""
    )
    op.execute(
        "CREATE INDEX ix_evidence_packs_ws ON evidence_packs (workspace_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE evidence_packs")
