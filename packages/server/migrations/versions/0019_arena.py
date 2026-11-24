"""arena tables (P5-6)

Revision ID: 0019
Revises: 0018
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE arena_handles (
            handle text PRIMARY KEY,
            created_at timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute(
        """CREATE TABLE arena_attempts (
            id text PRIMARY KEY,
            handle text NOT NULL REFERENCES arena_handles(handle),
            level integer NOT NULL,
            status text NOT NULL DEFAULT 'open',
            turns integer NOT NULL DEFAULT 0,
            started_at timestamptz NOT NULL DEFAULT now(),
            solved_at timestamptz,
            expires_at timestamptz NOT NULL,
            canary_digest text NOT NULL,
            reported boolean NOT NULL DEFAULT false,
            spent_usd_micros bigint NOT NULL DEFAULT 0,
            CONSTRAINT ck_arena_attempts_status
                CHECK (status IN ('open','solved','failed','expired')),
            CONSTRAINT ck_arena_attempts_level CHECK (level BETWEEN 1 AND 5)
        )"""
    )
    op.execute("CREATE INDEX ix_arena_attempts_handle ON arena_attempts (handle, started_at DESC)")
    op.execute(
        """CREATE TABLE arena_events (
            attempt_id text NOT NULL REFERENCES arena_attempts(id) ON DELETE CASCADE,
            seq integer NOT NULL,
            kind text NOT NULL,
            doc jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_arena_events PRIMARY KEY (attempt_id, seq)
        )"""
    )
    op.execute("CREATE INDEX ix_arena_events_created ON arena_events (created_at)")
    op.execute(
        """CREATE TABLE arena_solves (
            attempt_id text PRIMARY KEY REFERENCES arena_attempts(id) ON DELETE CASCADE,
            handle text NOT NULL REFERENCES arena_handles(handle),
            level integer NOT NULL,
            turns integer NOT NULL,
            seconds integer NOT NULL
        )"""
    )
    op.execute("CREATE INDEX ix_arena_solves_level ON arena_solves (level, turns, seconds)")


def downgrade() -> None:
    op.execute("DROP TABLE arena_solves")
    op.execute("DROP TABLE arena_events")
    op.execute("DROP TABLE arena_attempts")
    op.execute("DROP TABLE arena_handles")
