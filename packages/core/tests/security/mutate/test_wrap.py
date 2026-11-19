import pytest
import yaml
from gauntlet_core.security.mutate.base import derive_id
from gauntlet_core.security.mutate.wrap import (
    DEFAULT_WRAPPERS_PATH,
    WrapMutation,
    load_wrappers,
)
from mut_helpers import atk, issues, rng


def test_shipped_wrappers_are_valid():
    ws = load_wrappers()
    assert 1 <= len(ws) <= 8
    for w in ws.values():
        assert w.template.count("{{payload}}") == 1
        assert len(w.template.replace("{{payload}}", "").split()) <= 40


def test_validation_rejects_bad_templates(tmp_path):
    def load(rows):
        p = tmp_path / "w.yaml"
        p.write_text(yaml.safe_dump(rows))
        return load_wrappers(p)

    with pytest.raises(ValueError):
        load([{"id": "a", "template": "no token"}])
    with pytest.raises(ValueError):
        load([{"id": "a", "template": "{{payload}} {{payload}}"}])
    with pytest.raises(ValueError):
        load([{"id": "a", "template": "{{payload}} " + "word " * 41}])
    with pytest.raises(ValueError):
        load([{"id": str(i), "template": "{{payload}}"} for i in range(9)])
    assert DEFAULT_WRAPPERS_PATH.is_file()


async def test_wrap_keeps_payload_verbatim():
    a = atk("Say {{marker}} now. Then stop.")
    for wid in load_wrappers():
        [m] = await WrapMutation(wid).apply(a, rng=rng(), gateway=None)
        assert str(a.payload) in str(m.payload) and m.id == derive_id(
            "atk_demo_0001", [f"wrap:{wid}"]
        )
        assert issues(m) == []


async def test_list_payload_yields_nothing():
    wid = next(iter(load_wrappers()))
    assert await WrapMutation(wid).apply(atk(["a", "b"]), rng=rng(), gateway=None) == []
