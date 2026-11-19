import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from collections.abc import AsyncIterator

import pytest
from fake_server import FakeAgent, serve


@pytest.fixture
async def fake() -> AsyncIterator[FakeAgent]:
    async with serve(FakeAgent()) as state:
        yield state
