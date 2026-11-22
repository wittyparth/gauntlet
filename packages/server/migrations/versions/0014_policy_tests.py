"""policy_tests; runs.policy_id, policy_version, verify_of (P4-5)

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE policy_tests (
            id text PRIMARY KEY,
            workspace_id text NOT NULL REFERENCES workspaces(id),
            policy_id text NOT NULL,
            policy_version integer NOT NULL,
            agent_version_id text NOT NULL REFERENCES agent_versions(id),
            status text NOT NULL DEFAULT 'queued',
            result jsonb,
            attack_count integer NOT NULL DEFAULT 0,
            benign_count integer NOT NULL DEFAULT 0,
            error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz,
            CONSTRAINT ck_policy_tests_status
                CHECK (status IN ('queued','running','done','failed'))
        )"""
    )
    op.execute(
        "CREATE INDEX ix_policy_tests_policy "
        "ON policy_tests (workspace_id, policy_id, created_at DESC)"
    )
    op.execute("ALTER TABLE runs ADD COLUMN policy_id text")
    op.execute("ALTER TABLE runs ADD COLUMN policy_version integer")
    op.execute("ALTER TABLE runs ADD COLUMN verify_of text")
    op.execute("ALTER TABLE runs DROP CONSTRAINT ck_runs_purpose")
    op.execute(
        "ALTER TABLE runs ADD CONSTRAINT ck_runs_purpose CHECK (purpose IN ('eval','campaign',"
        "'replay','verify','import','verify_benign','verify_benign_baseline'))"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM episodes WHERE run_id IN "
        "(SELECT id FROM runs WHERE purpose LIKE 'verify_benign%')"
    )
    op.execute("DELETE FROM runs WHERE purpose LIKE 'verify_benign%'")
    op.execute("ALTER TABLE runs DROP CONSTRAINT ck_runs_purpose")
    op.execute(
        "ALTER TABLE runs ADD CONSTRAINT ck_runs_purpose "
        "CHECK (purpose IN ('eval','campaign','replay','verify','import'))"
    )
    op.execute("ALTER TABLE runs DROP COLUMN verify_of")
    op.execute("ALTER TABLE runs DROP COLUMN policy_version")
    op.execute("ALTER TABLE runs DROP COLUMN policy_id")
    op.execute("DROP TABLE policy_tests")
