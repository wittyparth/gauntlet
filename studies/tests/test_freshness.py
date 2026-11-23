from datetime import UTC, datetime

from studies.common import StudyResult, write_result
from studies.freshness import main


def _write(d, v):
    write_result(
        StudyResult(
            name="s", seed=0, platform_version=v, started_at=datetime(2026, 1, 1, tzinfo=UTC),
            metrics={}, n=0, limitations=["l"],
        ),
        d / "s.json",
    )  # fmt: skip


def test_stale_fails_current_passes(tmp_path):
    _write(tmp_path, "0.1.0")
    assert main(["--release", "0.2.0", "--results", str(tmp_path)]) == 1
    assert main(["--release", "0.1.0", "--results", str(tmp_path)]) == 0
    assert main(["--release", "0.0.9", "--results", str(tmp_path)]) == 0
