"""failure_embeddings, failure_clusters (P3-6). EMBED_DIM is fixed at 1536 (CQ-R7)

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = [
    """CREATE TABLE failure_embeddings (
        episode_id text PRIMARY KEY REFERENCES episodes(id),
        run_id text NOT NULL REFERENCES runs(id),
        embedding vector(1536) NOT NULL,
        text_hash text NOT NULL
    )""",
    "CREATE INDEX ix_failure_embeddings_run ON failure_embeddings (run_id)",
    """CREATE TABLE failure_clusters (
        id text PRIMARY KEY,
        run_id text NOT NULL REFERENCES runs(id),
        label integer NOT NULL,
        name text NOT NULL,
        description text NOT NULL DEFAULT '',
        suspected_cause text NOT NULL DEFAULT '',
        root_cause text NOT NULL,
        root_cause_share double precision NOT NULL,
        max_severity text,
        member_episode_ids jsonb NOT NULL,
        scenario_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
        exemplar_episode_id text,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX ix_failure_clusters_run ON failure_clusters (run_id, label)",
]


def upgrade() -> None:
    for stmt in _UP:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE failure_clusters")
    op.execute("DROP TABLE failure_embeddings")
