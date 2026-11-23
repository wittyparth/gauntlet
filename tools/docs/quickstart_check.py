"""Run the commands of docs/user/quickstart.md (blocks fenced as ```sh check) for real.

Offline: the scripted fake LLM answers, no model is called. `runs/quickstart` in the document is
swapped for a temp dir. Exit 0 when every command exits 0.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
import tempfile

from tools.docs._common import ROOT

QUICKSTART = ROOT / "docs" / "user" / "quickstart.md"
BLOCK = re.compile(r"```sh check\n(.*?)```", re.S)


def commands(text: str) -> list[str]:
    lines = [ln for block in BLOCK.findall(text) for ln in block.splitlines()]
    return [ln.removeprefix("$ ").strip() for ln in lines if ln.strip() and ln[0] != "#"]


def main() -> int:
    cmds = commands(QUICKSTART.read_text())
    if not cmds:
        print("no ```sh check blocks in quickstart.md", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        for cmd in cmds:
            real = cmd.replace("runs/quickstart", f"{tmp}/quickstart")
            print(f"$ {cmd}")
            res = subprocess.run(shlex.split(real), cwd=ROOT, capture_output=True, text=True)
            if res.returncode != 0:
                print(res.stdout[-1500:], res.stderr[-1500:], file=sys.stderr)
                print(f"FAILED (exit {res.returncode}): {cmd}", file=sys.stderr)
                return 1
    print(f"quickstart ok ({len(cmds)} commands)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
