"""production conversations and ingest counters (P5-1)

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE prod_conversations (
            id text PRIMARY KEY,
            workspace_id text NOT NULL REFERENCES workspaces(id),
            agent_id text REFERENCES agents(id),
            external_session_id text NOT NULL,
            started_at timestamptz NOT NULL,
            ended_at timestamptz NOT NULL,
            event_count integer NOT NULL DEFAULT 0,
            signals jsonb NOT NULL DEFAULT '{}'::jsonb,
            redaction jsonb NOT NULL DEFAULT '{}'::jsonb,
            run_id text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_prod_conversations_workspace_id UNIQUE (workspace_id, external_session_id)
        )"""
    )
    op.execute(
        "CREATE INDEX ix_prod_conversations_ws "
        "ON prod_conversations (workspace_id, started_at DESC)"
    )
    op.execute(
        """CREATE TABLE prod_events (
            conversation_id text NOT NULL REFERENCES prod_conversations(id) ON DELETE CASCADE,
            seq integer NOT NULL,
            kind text NOT NULL,
            doc jsonb NOT NULL,
            PRIMARY KEY (conversation_id, seq)
        )"""
    )
    op.execute(
        """CREATE TABLE prod_spans_seen (
            workspace_id text NOT NULL REFERENCES workspaces(id),
            trace_id text NOT NULL,
            span_id text NOT NULL,
            conversation_id text,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (workspace_id, trace_id, span_id)
        )"""
    )
    op.execute("CREATE INDEX ix_prod_spans_seen_created ON prod_spans_seen (created_at)")
    op.execute(
        """CREATE TABLE ingest_stats (
            workspace_id text NOT NULL REFERENCES workspaces(id),
            day date NOT NULL,
            spans bigint NOT NULL DEFAULT 0,
            bytes bigint NOT NULL DEFAULT 0,
            rejected bigint NOT NULL DEFAULT 0,
            redactions jsonb NOT NULL DEFAULT '{}'::jsonb,
            PRIMARY KEY (workspace_id, day)
        )"""
    )


def downgrade() -> None:
    for t in ("ingest_stats", "prod_spans_seen", "prod_events", "prod_conversations"):
        op.execute(f"DROP TABLE {t}")
