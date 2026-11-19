# gauntlet-server

The API process and the worker: FastAPI app, SQLAlchemy models, Alembic migrations, and the
Postgres implementations of the engine protocols (`PgJournalStore`, `PgEpisodeQueue`,
`PgBudgetLedger`).

Imports `gauntlet_core` only, never `gauntlet_cli` or `apps/web`.

Unit tests run anywhere. Postgres tests are marked `integration` and run when `TEST_DATABASE_URL`
points at the compose Postgres server (see `infra/README.md`); the tests use a dedicated `<db>_test` database on it (created on demand) so they never touch the live database or compete with the compose worker. Migrations: `alembic -c
packages/server/alembic.ini upgrade head` with `DATABASE_URL` set.
