"""mining_runs and mining_candidates (P5-2)

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE mining_runs (
            id text PRIMARY KEY,
            workspace_id text NOT NULL REFERENCES workspaces(id),
            agent_id text NOT NULL REFERENCES agents(id),
            "window" jsonb NOT NULL,
            status text NOT NULL DEFAULT 'queued',
            counts jsonb NOT NULL DEFAULT '{}'::jsonb,
            budget_usd_micros bigint NOT NULL,
            spent_usd_micros bigint NOT NULL DEFAULT 0,
            error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz,
            CONSTRAINT ck_mining_runs_status
                CHECK (status IN ('queued','running','done','failed'))
        )"""
    )
    op.execute("CREATE INDEX ix_mining_runs_ws ON mining_runs (workspace_id, created_at DESC)")
    op.execute(
        """CREATE TABLE mining_candidates (
            id text PRIMARY KEY,
            workspace_id text NOT NULL REFERENCES workspaces(id),
            mining_run_id text NOT NULL REFERENCES mining_runs(id) ON DELETE CASCADE,
            conversation_id text NOT NULL REFERENCES prod_conversations(id) ON DELETE CASCADE,
            score double precision NOT NULL,
            parts jsonb NOT NULL,
            reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
            detector_hits jsonb NOT NULL DEFAULT '[]'::jsonb,
            cluster_id text,
            cluster_name text,
            status text NOT NULL DEFAULT 'new',
            dismissed_reason text,
            scenario_id text,
            convert_error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_mining_candidates_mining_run_id UNIQUE (mining_run_id, conversation_id),
            CONSTRAINT ck_mining_candidates_status
                CHECK (status IN ('new','converted','dismissed'))
        )"""
    )
    op.execute(
        "CREATE INDEX ix_mining_candidates_run ON mining_candidates (mining_run_id, score DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE mining_candidates")
    op.execute("DROP TABLE mining_runs")
