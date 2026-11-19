import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = "tests/_fixtures/fixture_marked.py"


def run(**env: str) -> str:
    base = {k: v for k, v in os.environ.items() if not k.startswith(("TEST_DATABASE", "GAUNTLET_"))}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", FIXTURE, "-rs", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        env={**base, **env},
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout


def test_integration_skipped_without_database_url():
    out = run()
    assert "1 passed, 3 skipped" in out
    assert "needs compose services" in out


def test_integration_runs_with_database_url():
    out = run(TEST_DATABASE_URL="postgresql+asyncpg://x@localhost/x")
    assert "2 passed, 2 skipped" in out


def test_chaos_and_live_need_their_own_switches():
    out = run(
        TEST_DATABASE_URL="postgresql+asyncpg://x@localhost/x",
        GAUNTLET_CHAOS="1",
        GAUNTLET_LIVE="1",
    )
    assert "4 passed" in out
