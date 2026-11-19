from pg_helpers import isolated_url


def test_isolated_url_targets_a_dedicated_test_database():
    got = isolated_url("postgresql+asyncpg://u:p%40w@localhost:5433/gauntlet")
    assert got.endswith("@localhost:5433/gauntlet_test")
    assert "p%40w" in got


def test_isolated_url_is_idempotent():
    url = "postgresql+asyncpg://u:p@h/x_test"
    assert isolated_url(url) == url
