"""The dev seed finds packs/ecommerce in a checkout and inside the container image."""

from __future__ import annotations

from pathlib import Path

import pytest
from gauntlet_server.services.seed import resolve_pack_dir


def make_pack(root: Path) -> Path:
    d = root / "packs" / "ecommerce"
    d.mkdir(parents=True)
    (d / "pack.yaml").write_text("id: ecommerce\n")
    return d


def test_env_wins(tmp_path: Path):
    assert resolve_pack_dir({"GAUNTLET_PACK_DIR": "/x/y"}) == Path("/x/y")


def test_container_layout_found_from_the_working_directory(tmp_path: Path):
    """Installed in site-packages: the source-relative path points at /app/.venv/lib."""
    expected = make_pack(tmp_path / "app")
    site = tmp_path / "app/.venv/lib/python3.12/site-packages/gauntlet_server/services/seed.py"
    assert resolve_pack_dir({}, here=site, cwd=tmp_path / "app") == expected


def test_checkout_layout_found_from_the_source(tmp_path: Path):
    expected = make_pack(tmp_path)
    here = tmp_path / "packages/server/src/gauntlet_server/services/seed.py"
    assert resolve_pack_dir({}, here=here, cwd=Path("/")) == expected


def test_missing_pack_is_a_clear_error(tmp_path: Path):
    here = tmp_path / "a/b/c/d/e/f/seed.py"
    with pytest.raises(FileNotFoundError, match="GAUNTLET_PACK_DIR"):
        resolve_pack_dir({}, here=here, cwd=tmp_path)
