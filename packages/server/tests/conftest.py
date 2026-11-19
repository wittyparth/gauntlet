import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "stores"))

from pg_fixtures import migrated_url, sm  # noqa: F401
