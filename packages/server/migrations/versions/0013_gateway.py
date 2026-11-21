"""gateway_decisions and gateway_approvals (P4-2)

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE gateway_decisions (
            id text PRIMARY KEY,
            workspace_id text NOT NULL REFERENCES workspaces(id),
            ts timestamptz NOT NULL,
            session_id text NOT NULL,
            agent_id text,
            policy_id text NOT NULL,
            policy_version integer NOT NULL,
            mode text NOT NULL,
            kind text NOT NULL,
            tool text,
            action text NOT NULL,
            enforced boolean NOT NULL,
            rule_id text,
            severity text,
            overhead_us integer NOT NULL,
            doc jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_gateway_decisions_mode CHECK (mode IN ('shadow','enforce')),
            CONSTRAINT ck_gateway_decisions_kind CHECK (kind IN ('tool_call','output')),
            CONSTRAINT ck_gateway_decisions_action
                CHECK (action IN ('allow','block','require_approval','redact','log'))
        )"""
    )
    op.execute(
        "CREATE INDEX ix_gateway_decisions_ws_ts "
        "ON gateway_decisions (workspace_id, ts DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX ix_gateway_decisions_policy "
        "ON gateway_decisions (workspace_id, policy_id, ts)"
    )
    op.execute(
        """CREATE TABLE gateway_approvals (
            id text PRIMARY KEY,
            workspace_id text NOT NULL REFERENCES workspaces(id),
            decision_doc jsonb NOT NULL,
            status text NOT NULL,
            requested_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            decided_by text,
            decided_at timestamptz,
            note text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_gateway_approvals_status
                CHECK (status IN ('pending','approved','denied','expired'))
        )"""
    )
    op.execute(
        "CREATE INDEX ix_gateway_approvals_ws_status ON gateway_approvals (workspace_id, status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE gateway_approvals")
    op.execute("DROP TABLE gateway_decisions")
