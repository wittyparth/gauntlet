"""The Phase 2 catalog rows and oracle signatures equal the registry; oracles parse."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from dva.config import world_file
from dva.flaws import FLAWS
from dva.recall import parse_oracle
from gauntlet_core.schema import WorldSpec, load_yaml
from gauntlet_core.security import load_taxonomy

CATALOG = Path(__file__).parents[1] / "CATALOG.md"
ROOT = Path(__file__).parents[3]


def oracle_rows() -> dict[str, tuple[str, str]]:
    body = CATALOG.read_text().split("<!-- oracles:start -->")[1].split("<!-- oracles:end -->")[0]
    rows = {}
    for ln in body.splitlines():
        m = re.match(r"\| (F\d\d) \| (\w+) \| `(.*)` \|$", ln)
        if m:
            rows[m[1]] = (m[2], m[3].replace("\\|", "|"))
    return rows


def test_ids_are_f01_to_f25_and_f30_to_f35():
    want = [f"F{n:02d}" for n in [*range(1, 26), *range(30, 36), *range(40, 47), *range(50, 59)]]
    assert list(FLAWS) == want


def test_oracle_table_equals_the_registry():
    assert oracle_rows() == {f.id: (f.agent, f.oracle) for f in FLAWS.values() if f.oracle}


def test_every_non_empty_oracle_parses_and_f25_is_the_expected_miss():
    for f in FLAWS.values():
        if f.oracle:
            assert parse_oracle(f.oracle), f.id
    assert FLAWS["F25"].oracle == "" and FLAWS["F25"].agent == "sql"


@pytest.mark.parametrize(
    "bad", ["nonsense:x", "tool_called", "canary_leaked:tool_args:x", "tool_called:t~("]
)
def test_unparsable_oracles_are_rejected(bad):
    with pytest.raises(ValueError):
        parse_oracle(bad)  # includes re.error, a ValueError subclass


def test_flaw_categories_are_in_the_taxonomy_and_agents_known():
    ids = set(load_taxonomy(ROOT / "attacks" / "taxonomy.yaml").ids())
    for f in FLAWS.values():
        assert f.agent in ("support", "sql", "email", "copilot", "banking")
        assert set(f.category.split(",")) <= ids, f.id
        if f.phase == 2 and f.agent != "support":
            assert f.detect_by == ("phase2:recall",)


def test_worlds_exist_for_both_variants_and_plant_the_canaries():
    for agent, canary in (("sql", "cred_key"), ("email", "other_mail_secret")):
        for variant in ("unfixed", "fixed"):
            w = load_yaml(WorldSpec, world_file(agent, variant))
            assert canary in {c.id for c in w.canaries} and any(t.honeytool for t in w.tools)
