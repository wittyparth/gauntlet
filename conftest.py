"""Repo-wide pytest plumbing: skip rules for tests that need external services.

* `integration`: needs compose services, runs only when TEST_DATABASE_URL is set.
* `chaos`: integration plus GAUNTLET_CHAOS=1.
* `live`: calls real models, needs GAUNTLET_LIVE=1.
"""

from __future__ import annotations

import os

import pytest


def _skip_reason(item: pytest.Item) -> str | None:
    if "integration" in item.keywords and not os.environ.get("TEST_DATABASE_URL"):
        return "needs compose services (set TEST_DATABASE_URL)"
    if "chaos" in item.keywords and os.environ.get("GAUNTLET_CHAOS") != "1":
        return "needs GAUNTLET_CHAOS=1"
    if "live" in item.keywords and os.environ.get("GAUNTLET_LIVE") != "1":
        return "needs GAUNTLET_LIVE=1"
    return None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        reason = _skip_reason(item)
        if reason:
            item.add_marker(pytest.mark.skip(reason=reason))
