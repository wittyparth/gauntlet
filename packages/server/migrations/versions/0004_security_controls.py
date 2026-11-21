"""ownership verifications, immutable audit log, kill switches, workspace settings doc

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATEMENTS = [
    """CREATE TABLE target_verifications (
        id text PRIMARY KEY,
        workspace_id text NOT NULL REFERENCES workspaces(id),
        host text NOT NULL,
        method text NOT NULL,
        token text NOT NULL,
        status text NOT NULL DEFAULT 'pending',
        verified_at timestamptz,
        expires_at timestamptz,
        last_checked_at timestamptz,
        detail text,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_target_verifications_workspace_id UNIQUE (workspace_id, host),
        CONSTRAINT ck_target_verifications_method CHECK (method IN ('dns','http')),
        CONSTRAINT ck_target_verifications_status
            CHECK (status IN ('pending','verified','failed','expired'))
    )""",
    """CREATE TABLE audit_log (
        id text PRIMARY KEY,
        workspace_id text NOT NULL REFERENCES workspaces(id),
        ts timestamptz NOT NULL,
        actor text NOT NULL,
        action text NOT NULL,
        subject_type text NOT NULL,
        subject_id text NOT NULL,
        detail jsonb NOT NULL DEFAULT '{}'::jsonb,
        prev_hash text NOT NULL,
        hash text NOT NULL,
        seq bigserial,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX ix_audit_log_ws ON audit_log (workspace_id, seq)",
    """CREATE FUNCTION audit_log_immutable() RETURNS trigger AS $$
       BEGIN RAISE EXCEPTION 'audit_log is append-only'; END;
       $$ LANGUAGE plpgsql""",
    """CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log
       FOR EACH ROW EXECUTE FUNCTION audit_log_immutable()""",
    """CREATE TABLE kill_switches (
        id text PRIMARY KEY,
        workspace_id text NOT NULL REFERENCES workspaces(id),
        scope text NOT NULL,
        run_id text,
        engaged_by text NOT NULL,
        reason text NOT NULL,
        engaged_at timestamptz NOT NULL DEFAULT now(),
        released_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_kill_switches_scope CHECK (scope IN ('workspace','run'))
    )""",
    "ALTER TABLE workspace_settings ADD COLUMN doc jsonb NOT NULL DEFAULT '{}'::jsonb",
]


def upgrade() -> None:
    for sql in _STATEMENTS:
        op.execute(sql)


def downgrade() -> None:
    op.execute("ALTER TABLE workspace_settings DROP COLUMN doc")
    op.execute("DROP TABLE kill_switches")
    op.execute("DROP TABLE audit_log")
    op.execute("DROP FUNCTION audit_log_immutable()")
    op.execute("DROP TABLE target_verifications")
