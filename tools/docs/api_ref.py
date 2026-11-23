"""Generate docs/user/reference/api.md from the server's OpenAPI document."""

from __future__ import annotations

import sys
from typing import Any

from tools.docs._common import BANNER, write_or_check


def render() -> dict[str, str]:
    from gauntlet_server.app import create_app

    spec: dict[str, Any] = create_app().openapi()
    by_tag: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for path, item in sorted(spec["paths"].items()):
        for method, op in sorted(item.items()):
            tag = (op.get("tags") or [path.split("/")[2] if path.count("/") > 1 else "root"])[0]
            by_tag.setdefault(tag, []).append((method.upper(), path, op))
    out = [
        BANNER.format(gen="tools/docs/api_ref.py", mod="api_ref") + "# REST API reference\n",
        f"Generated from the OpenAPI document (`{spec['info']['title']}` "
        f"{spec['info']['version']}). Authenticate with `Authorization: Bearer gk_...`. "
        "The live document is served at `/openapi.json`.\n",
    ]
    for tag in sorted(by_tag):
        out += [f"## {tag}\n", "| Method | Path | Summary |", "|---|---|---|"]
        for method, path, op in by_tag[tag]:
            summary = (op.get("summary") or "").replace("|", "/")
            out.append(f"| `{method}` | `{path}` | {summary} |")
        out.append("")
    return {"api.md": "\n".join(out) + "\n"}


def main(argv: list[str] | None = None) -> int:
    return write_or_check(render(), sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
