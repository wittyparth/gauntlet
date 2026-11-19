import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

REPO = Path(__file__).parents[4]


@pytest.fixture(scope="session")
def pack():
    from gauntlet_core.packs import load_pack

    return load_pack(REPO / "packs" / "ecommerce")
