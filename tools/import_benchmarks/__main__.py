"""`uv run python -m tools.import_benchmarks tau-bench|agentdojo --src DIR --out DIR --pin PIN`."""

from __future__ import annotations

import argparse
from pathlib import Path

from .agentdojo import import_agentdojo
from .tau_bench import import_tau_bench


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="import_benchmarks")
    ap.add_argument("which", choices=["tau-bench", "agentdojo"])
    ap.add_argument("--src", type=Path, required=True, help="upstream checkout")
    ap.add_argument("--out", type=Path, required=True, help="pack directory to write")
    ap.add_argument("--pin", required=True, help="upstream commit (tau-bench) or version")
    ap.add_argument("--suite", default="banking", help="agentdojo suite: banking or slack")
    ap.add_argument("--allow-unpinned", action="store_true", help="run with a different pin")
    a = ap.parse_args(argv)
    if a.which == "tau-bench":
        report = import_tau_bench(a.src, a.out, pin=a.pin, allow_unpinned=a.allow_unpinned)
    else:
        report = import_agentdojo(
            a.src, a.out, suite=a.suite, pin=a.pin, allow_unpinned=a.allow_unpinned
        )
    print(report.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
