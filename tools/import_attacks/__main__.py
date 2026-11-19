"""`python -m tools.import_attacks <source> --src PATH --pin PIN [--out attacks/library]`.

The importer never downloads anything: `--src` is a local checkout (or, for garak and
AgentDojo, the isolated environment's installed package is used). Run garak and AgentDojo as
`uv run --with "garak==<ver>" python -m tools.import_attacks garak ...`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import agentdojo, garak, injecagent, promptfoo
from .common import (
    REPO_ROOT,
    SOURCE_PRIORITY,
    Skip,
    build_attacks,
    existing_hashes,
    load_mapping,
    update_skipped,
    write_library,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tools.import_attacks")
    ap.add_argument("source", choices=list(SOURCE_PRIORITY))
    ap.add_argument("--src", type=Path, default=None)
    ap.add_argument("--pin", required=True)
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "attacks" / "library")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-per-probe", type=int, default=5)
    a = ap.parse_args(argv)

    m = load_mapping(a.source)
    skips: list[Skip]
    if a.source == "garak":
        cands, skips = garak.read_candidates(a.src, max_per_probe=a.max_per_probe)
    elif a.source == "agentdojo":
        cands, skips = agentdojo.read_candidates(a.src)
    else:
        if a.src is None:
            ap.error("--src is required for this source")
        reader = injecagent if a.source == "injecagent" else promptfoo
        cands, skips = reader.read_candidates(a.src)
    higher = SOURCE_PRIORITY[: SOURCE_PRIORITY.index(a.source)]
    attacks, more = build_attacks(
        cands,
        source=a.source,
        project=m["project"],
        pin=a.pin,
        license_id=m["license"],
        severities=m["severity"],
        seed=a.seed,
        max_per_group=int(m.get("group_cap", a.max_per_probe)),
        seen_hashes=existing_hashes(a.out, higher),
    )
    write_library(attacks, a.out, a.source)
    update_skipped(a.out, a.source, [*skips, *more])
    print(f"{a.source}: {len(attacks)} imported, {len(skips) + len(more)} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
