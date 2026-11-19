from __future__ import annotations

import re
from pathlib import Path

from dva.flaws import FLAWS
from dva_helpers import pack

CATALOG = Path(__file__).parents[1] / "CATALOG.md"


def registry_rows() -> list[list[str]]:
    rows = []
    for f in FLAWS.values():
        variants = "both" if len(f.variants) == 2 else "wired"
        rows.append(
            [f.id, f.title, f.how, variants, f.category, str(f.phase), ", ".join(f.detect_by)]
        )
    return rows


def catalog_rows() -> list[list[str]]:
    text = CATALOG.read_text()
    body = text.split("<!-- catalog:start -->")[1].split("<!-- catalog:end -->")[0]
    lines = [ln for ln in body.strip().splitlines() if ln.startswith("| F")]
    return [[c.strip() for c in ln.strip("|").split("|")] for ln in lines]


def test_catalog_rows_equal_the_registry():
    assert catalog_rows() == registry_rows()


def test_ids_f01_to_f19_unique_and_ordered():
    assert list(FLAWS) == [f"F{n:02d}" for n in range(1, 20)]


def test_every_phase1_detect_by_scenario_exists_in_the_pack():
    for f in FLAWS.values():
        for target in f.detect_by:
            if f.phase == 1:
                assert target in pack().scenarios, (f.id, target)
            else:
                assert target.startswith("phase")


def test_reproduction_notes_cover_every_phase1_flaw():
    notes = CATALOG.read_text().split("## Reproduction notes")[1]
    assert set(re.findall(r"^\| (F\d\d) \|", notes, re.M)) == {
        f.id for f in FLAWS.values() if f.phase == 1
    }


def test_no_forbidden_model_ids_anywhere():
    root = Path(__file__).parents[1]
    for path in [*root.rglob("*.py"), *root.rglob("*.md"), *root.rglob("*.yaml")]:
        if "tests" in path.parts and path.name == "test_catalog.py":
            continue
        text = path.read_text()
        assert "openai/" not in text and "anthropic/" not in text, path
