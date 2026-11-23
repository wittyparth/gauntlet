"""Generate the check-language and threat-taxonomy references."""

from __future__ import annotations

import json
import sys

from gauntlet_core.schema import checks
from gauntlet_core.security.taxonomy import load_taxonomy
from pydantic import TypeAdapter

from tools.docs._common import BANNER, write_or_check


def render() -> dict[str, str]:
    schema = TypeAdapter(checks.Check).json_schema()
    kinds = sorted(
        {
            d["properties"]["kind"]["const"]
            for d in schema["$defs"].values()
            if "const" in d.get("properties", {}).get("kind", {})
        }
    )
    check = [
        BANNER.format(gen="tools/docs/check_ref.py", mod="check_ref") + "# Check language\n",
        "Checks are JSON or YAML documents validated by this JSON Schema (generated from the "
        "Pydantic models). Check kinds: " + ", ".join(f"`{k}`" for k in kinds) + ".\n",
        "```json",
        json.dumps(schema, indent=1, sort_keys=True),
        "```\n",
    ]
    tax = load_taxonomy()
    rows = [
        BANNER.format(gen="tools/docs/check_ref.py", mod="check_ref") + "# Threat taxonomy\n",
        f"Verified on {tax.verified_on}. Mapped to OWASP LLM, OWASP Agentic and MITRE ATLAS ids.\n",
        "| # | Category | OWASP LLM | OWASP Agentic | ATLAS | Scope |",
        "|---|---|---|---|---|---|",
    ]
    for c in tax.categories:
        rows.append(
            f"| {c.number} | **{c.title}** (`{c.id}`): {c.description.strip()} "
            f"| {', '.join(c.owasp_llm)} | {', '.join(c.owasp_agentic)} "
            f"| {', '.join(c.atlas)} | {c.phase_scope} |".replace("\n", " ")
        )
    return {"check-language.md": "\n".join(check), "taxonomy.md": "\n".join(rows) + "\n"}


def main(argv: list[str] | None = None) -> int:
    return write_or_check(render(), sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
