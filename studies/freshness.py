"""Release gate: exit 1 when any result file's `platform_version` is older than the release."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .common import RESULTS_DIR, load_results, version_tuple


def stale(release: str, directory: Path | None = None) -> list[str]:
    want = version_tuple(release)
    return [
        f"{r.name} ({r.platform_version})"
        for r in load_results(directory)
        if version_tuple(r.platform_version) < want
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="studies.freshness")
    ap.add_argument("--release", required=True)
    ap.add_argument("--results", type=Path, default=RESULTS_DIR)
    ns = ap.parse_args(argv)
    bad = stale(ns.release, ns.results)
    for b in bad:
        print(f"stale: {b} is older than release {ns.release}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
