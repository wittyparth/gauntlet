"""Generate docs/user/reference/cli.md from the Typer app (deterministic, no terminal width)."""

from __future__ import annotations

import sys
from typing import Any

import typer.main
from gauntlet_cli.main import app

from tools.docs._common import BANNER, ROOT, write_or_check


def _option(p: Any) -> str:
    if type(p).__name__ == "Argument":
        return f"| `{p.name}` | {'required' if p.required else 'optional'} argument | |"
    names = ", ".join(f"`{o}`" for o in p.opts)
    default = p.default
    shown = "" if default in (None, False, ()) or callable(default) else f"`{default}`"
    shown = shown.replace(str(ROOT), "<repo>")
    env = f" (env `{p.envvar}`)" if isinstance(p.envvar, str) else ""
    return f"| {names} | {shown} | {(p.help or '').replace('|', '/')}{env} |"


def _walk(cmd: Any, path: list[str], out: list[str]) -> None:
    level = "#" * min(len(path) + 1, 4)
    out.append(f"{level} `{' '.join(path)}`\n")
    if cmd.help:
        out.append(cmd.help.split("\n\n")[0].replace("\n", " ") + "\n")
    params = [p for p in cmd.params if p.name != "help"]
    if params:
        out += ["| Name | Default | Description |", "|---|---|---|"]
        out += [_option(p) for p in params]
        out.append("")
    if getattr(cmd, "commands", None):
        for name in sorted(cmd.commands):
            _walk(cmd.commands[name], [*path, name], out)


def render() -> dict[str, str]:
    root = typer.main.get_command(app)
    out = [
        BANNER.format(gen="tools/docs/cli_ref.py", mod="cli_ref") + "# CLI reference\n",
        "Every command of `gauntlet`, generated from the Typer app.\n",
    ]
    _walk(root, ["gauntlet"], out)
    return {"cli.md": "\n".join(out) + "\n"}


def main(argv: list[str] | None = None) -> int:
    return write_or_check(render(), sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
