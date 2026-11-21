"""human_labels, calibrations, jobs (P3-5)

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = [
    """CREATE TABLE human_labels (
        id text PRIMARY KEY,
        workspace_id text NOT NULL REFERENCES workspaces(id),
        episode_id text NOT NULL REFERENCES episodes(id),
        rubric_id text NOT NULL,
        rubric_version integer,
        result text NOT NULL,
        labeler text NOT NULL,
        note text,
        is_golden boolean NOT NULL DEFAULT false,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_human_labels_result CHECK (result IN ('pass','fail','na')),
        CONSTRAINT uq_human_labels_episode_id UNIQUE (episode_id, rubric_id, labeler)
    )""",
    "CREATE INDEX ix_human_labels_ws ON human_labels (workspace_id, rubric_id)",
    """CREATE TABLE calibrations (
        id text PRIMARY KEY,
        workspace_id text NOT NULL REFERENCES workspaces(id),
        rubric_id text NOT NULL,
        rubric_version integer NOT NULL,
        judge_models jsonb NOT NULL DEFAULT '{}'::jsonb,
        status text NOT NULL DEFAULT 'queued',
        result jsonb,
        golden_count integer NOT NULL DEFAULT 0,
        gating_allowed boolean NOT NULL DEFAULT false,
        threshold double precision,
        stale boolean NOT NULL DEFAULT false,
        error text,
        cost_usd_micros bigint NOT NULL DEFAULT 0,
        created_at timestamptz NOT NULL DEFAULT now(),
        finished_at timestamptz,
        CONSTRAINT ck_calibrations_status CHECK (status IN ('queued','running','done','failed'))
    )""",
    "CREATE INDEX ix_calibrations_rubric "
    "ON calibrations (workspace_id, rubric_id, created_at DESC)",
    """CREATE TABLE jobs (
        id text PRIMARY KEY,
        workspace_id text NOT NULL REFERENCES workspaces(id),
        kind text NOT NULL,
        payload jsonb NOT NULL DEFAULT '{}'::jsonb,
        status text NOT NULL DEFAULT 'queued',
        result jsonb,
        error text,
        attempts integer NOT NULL DEFAULT 0,
        lease_owner text,
        lease_expires_at timestamptz,
        not_before timestamptz NOT NULL DEFAULT now(),
        created_at timestamptz NOT NULL DEFAULT now(),
        finished_at timestamptz,
        CONSTRAINT ck_jobs_status CHECK (status IN ('queued','running','done','failed'))
    )""",
    "CREATE INDEX ix_jobs_claim ON jobs (created_at) WHERE status IN ('queued','running')",
]


def upgrade() -> None:
    for stmt in _UP:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE jobs")
    op.execute("DROP TABLE calibrations")
    op.execute("DROP TABLE human_labels")
