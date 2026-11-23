"""`uv run python -m benchmarks.reproduction run --suite taubench_retail --model <catalog id>
--trials 4 [--smoke] [--cassette-dir DIR]` and `... report`."""

from __future__ import annotations

import argparse
from pathlib import Path

from .harness import CONFIG, RESULTS, run_suite
from .report import render


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="benchmarks.reproduction")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a suite and write a result file")
    r.add_argument("--suite", required=True)
    r.add_argument("--model", required=True, help="a catalog model id")
    r.add_argument("--trials", type=int, default=4)
    r.add_argument("--smoke", action="store_true", help="the smoke subset only")
    r.add_argument("--pack", type=Path, help="imported pack directory (default: config.yaml)")
    r.add_argument("--cassette-dir", type=Path, help="replay a scripted transcript, spend nothing")
    sub.add_parser("report", help="render the comparison table from results/")
    a = ap.parse_args(argv)
    if a.cmd == "report":
        print(render(RESULTS, CONFIG), end="")
        return 0
    path = run_suite(
        suite=a.suite,
        model=a.model,
        trials=a.trials,
        smoke=a.smoke,
        pack_dir=a.pack,
        cassette_dir=a.cassette_dir,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
