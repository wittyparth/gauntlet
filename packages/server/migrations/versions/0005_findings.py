"""findings, finding_episodes, attacks, episode_attacks, runs.purpose and finding_id

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATEMENTS = [
    """CREATE TABLE findings (
        id text PRIMARY KEY,
        workspace_id text NOT NULL REFERENCES workspaces(id),
        agent_version_id text NOT NULL REFERENCES agent_versions(id),
        category text NOT NULL,
        severity text NOT NULL,
        status text NOT NULL DEFAULT 'open',
        dedup_key text NOT NULL,
        title text NOT NULL,
        attack_id text,
        repro_successes int NOT NULL DEFAULT 0,
        repro_attempts int NOT NULL DEFAULT 0,
        doc jsonb NOT NULL,
        notes jsonb NOT NULL DEFAULT '[]'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_findings_workspace_id UNIQUE (workspace_id, agent_version_id, dedup_key)
    )""",
    "CREATE INDEX ix_findings_ws ON findings (workspace_id, created_at DESC)",
    """CREATE TABLE finding_episodes (
        finding_id text NOT NULL,
        CONSTRAINT fk_finding_episodes_finding_id_findings FOREIGN KEY (finding_id)
            REFERENCES findings(id),
        episode_id text NOT NULL,
        role text NOT NULL DEFAULT 'evidence',
        evidence_seqs int[] NOT NULL DEFAULT '{}',
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (finding_id, episode_id),
        CONSTRAINT ck_finding_episodes_role
            CHECK (role IN ('evidence','variant','verification','replay'))
    )""",
    """CREATE TABLE attacks (
        id text PRIMARY KEY,
        workspace_id text NOT NULL REFERENCES workspaces(id),
        doc jsonb NOT NULL,
        category text NOT NULL,
        vector text NOT NULL,
        source text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE episode_attacks (
        episode_id text PRIMARY KEY,
        workspace_id text NOT NULL REFERENCES workspaces(id),
        attack_id text NOT NULL,
        category text NOT NULL,
        vector text NOT NULL,
        objective_held boolean NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX ix_episode_attacks_ws ON episode_attacks (workspace_id, category)",
    "ALTER TABLE runs ADD COLUMN purpose text NOT NULL DEFAULT 'eval'",
    "ALTER TABLE runs ADD COLUMN finding_id text",
    "ALTER TABLE runs ADD COLUMN attack boolean NOT NULL DEFAULT false",
    "ALTER TABLE runs ADD CONSTRAINT ck_runs_purpose "
    "CHECK (purpose IN ('eval','campaign','replay','verify'))",
]


def upgrade() -> None:
    for sql in _STATEMENTS:
        op.execute(sql)


def downgrade() -> None:
    op.execute("ALTER TABLE runs DROP CONSTRAINT ck_runs_purpose")
    op.execute("ALTER TABLE runs DROP COLUMN attack")
    op.execute("ALTER TABLE runs DROP COLUMN finding_id")
    op.execute("ALTER TABLE runs DROP COLUMN purpose")
    for t in ("episode_attacks", "attacks", "finding_episodes", "findings"):
        op.execute(f"DROP TABLE {t}")
