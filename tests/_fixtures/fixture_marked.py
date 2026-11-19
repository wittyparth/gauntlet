"""Run by test_marker_plumbing in a subprocess; not collected by the normal run."""

import pytest


@pytest.mark.integration
def test_integration_marked():
    pass


@pytest.mark.live
def test_live_marked():
    pass


@pytest.mark.chaos
def test_chaos_marked():
    pass


def test_unmarked():
    pass
