# gauntlet-core

The engine and everything that must be deterministic and testable without a server: schema models,
durable episode execution (journal, effects, queue protocol, memory and SQLite stores), mock world,
checks, judges, statistics, LLM gateway.

Imports nothing from `gauntlet_server` or `gauntlet_cli`. No web framework, no Postgres driver.
Public API is whatever each subpackage `__init__.py` exports in `__all__`.

Test: `uv run pytest packages/core -q`.
