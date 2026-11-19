# Local infrastructure

Postgres 16 with pgvector, Redis 7, MinIO, plus the `api` and `worker` services.

```sh
cp infra/.env.example infra/.env          # placeholders only; edit locally, never commit
export OPENROUTER_API_KEY=...             # optional, passed through by compose
docker compose -f infra/docker-compose.yml up -d --build --wait
curl -fs localhost:8000/healthz
```

| Service | Host port | Notes |
|---|---|---|
| postgres | 5432 (`POSTGRES_HOST_PORT`) | databases `gauntlet` and `gauntlet_test`, both with `vector` |
| redis | 6379 (`REDIS_HOST_PORT`) | cache and pub/sub only |
| minio | 9000 S3, 9001 console | bucket `gauntlet` created by `minio-init` |
| api | 8000 | `GET /healthz` |
| worker | none | scale with `up -d --scale worker=3` |

All ports bind to 127.0.0.1. If a local Postgres already owns 5432, set `POSTGRES_HOST_PORT=5433`
in `infra/.env` and use the same port in `TEST_DATABASE_URL`.

`migrate` runs `alembic upgrade head` against `DATABASE_URL` before `api` and `worker` start.

Run the integration tests from the host:

```sh
set -a; . infra/.env; set +a
uv run pytest tests/integration -q
uv run pytest packages -q -m integration
```

Reset everything (drops all data): `docker compose -f infra/docker-compose.yml down -v`.
Stop and keep data: `docker compose -f infra/docker-compose.yml down`.
