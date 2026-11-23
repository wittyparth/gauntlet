"""schedules, slos, alert channels, rules and alerts (P5-7)

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE schedules (
            id text PRIMARY KEY,
            workspace_id text NOT NULL REFERENCES workspaces(id),
            agent_version_id text NOT NULL REFERENCES agent_versions(id),
            suite_id text NOT NULL REFERENCES suites(id),
            cron text NOT NULL,
            timezone text NOT NULL DEFAULT 'UTC',
            budget_usd_micros integer NOT NULL,
            enabled boolean NOT NULL DEFAULT true,
            last_fired_at timestamptz,
            next_fire_at timestamptz,
            last_run_id text,
            last_status text,
            skipped_budget integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX ix_schedules_due ON schedules (enabled, next_fire_at)")
    op.execute(
        """CREATE TABLE slos (
            id text PRIMARY KEY,
            workspace_id text NOT NULL REFERENCES workspaces(id),
            agent_id text NOT NULL REFERENCES agents(id),
            metric text NOT NULL,
            objective double precision NOT NULL,
            window_days integer NOT NULL,
            burn_alerts jsonb NOT NULL DEFAULT '[]'::jsonb,
            enabled boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_slos_metric CHECK (metric IN ('pass_rate','attack_success_rate',
                'latency_p95','cost_per_episode','prod_failure_rate'))
        )"""
    )
    op.execute("CREATE INDEX ix_slos_ws ON slos (workspace_id, agent_id)")
    op.execute(
        """CREATE TABLE alert_channels (
            id text PRIMARY KEY,
            workspace_id text NOT NULL REFERENCES workspaces(id),
            kind text NOT NULL,
            secret_name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_alert_channels_kind CHECK (kind IN ('webhook','slack','email'))
        )"""
    )
    op.execute("CREATE INDEX ix_alert_channels_ws ON alert_channels (workspace_id)")
    op.execute(
        """CREATE TABLE alert_rules (
            id text PRIMARY KEY,
            workspace_id text NOT NULL REFERENCES workspaces(id),
            slo_id text REFERENCES slos(id) ON DELETE CASCADE,
            kind text NOT NULL,
            params jsonb NOT NULL DEFAULT '{}'::jsonb,
            channel_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
            silence_until timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_alert_rules_kind
                CHECK (kind IN ('burn','breach','finding','gateway_block_rate'))
        )"""
    )
    op.execute("CREATE INDEX ix_alert_rules_ws ON alert_rules (workspace_id)")
    op.execute(
        """CREATE TABLE alerts (
            id text PRIMARY KEY,
            workspace_id text NOT NULL REFERENCES workspaces(id),
            rule_id text NOT NULL REFERENCES alert_rules(id) ON DELETE CASCADE,
            fingerprint text NOT NULL,
            state text NOT NULL,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            first_at timestamptz NOT NULL,
            last_at timestamptz NOT NULL,
            notified_at timestamptz,
            notified_state text,
            CONSTRAINT uq_alerts_rule_id UNIQUE (rule_id, fingerprint),
            CONSTRAINT ck_alerts_state CHECK (state IN ('firing','resolved'))
        )"""
    )
    op.execute("CREATE INDEX ix_alerts_ws ON alerts (workspace_id, state)")


def downgrade() -> None:
    for t in ("alerts", "alert_rules", "alert_channels", "slos", "schedules"):
        op.execute(f"DROP TABLE {t}")
