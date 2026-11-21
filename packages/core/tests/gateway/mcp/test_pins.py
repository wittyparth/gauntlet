import copy
import json

import pytest
from gauntlet_core.gateway.mcp import (
    PinStore,
    canonical_tool,
    server_manifest_hash,
    tool_pin_hash,
)
from gauntlet_core.security.scan import scan_mcp_tools

READ = {
    "name": "read_file",
    "description": "Read a file from disk.",
    "inputSchema": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    "annotations": {"readOnlyHint": True},
}
WRITE = {
    "name": "write_file",
    "title": "Write File",
    "description": "Write text to a file.",
    "inputSchema": {
        "type": "object",
        "properties": {"path": {"type": "string"}, "text": {"type": "string"}},
    },
    "outputSchema": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
    "annotations": {"destructiveHint": True},
}
PING = {"name": "ping", "inputSchema": {"type": "object"}}

# Written down on purpose: an accidental change to the canonicalisation breaks these.
EXPECTED = {
    "read_file": "sha256:ae7bcb65a3fb73e4007f53bdac18756f52de8b3b35e751d2600bf29938acade5",
    "write_file": "sha256:e3173198029a7f02fe7225db26220038b58dadaefb6a069384f48bdbac066eb7",
    "ping": "sha256:50f729fba0aa51f78cf94c1ca23fd07f217375133d9c20b0764d808d56c61db9",
}
MANIFEST = "sha256:afb8d556b6d4344d712b555b3bf8f0de4aa56b5aede9ff4e53e738128938e9fb"


def test_fixed_digests():
    assert {t["name"]: tool_pin_hash(t) for t in (READ, WRITE, PING)} == EXPECTED
    assert server_manifest_hash(EXPECTED) == MANIFEST
    assert server_manifest_hash(dict(reversed(EXPECTED.items()))) == MANIFEST  # order free


def test_canonical_form():
    assert canonical_tool(PING) == '{"inputSchema":{"type":"object"},"name":"ping"}'


def test_zero_width_character_changes_the_hash():
    poisoned = {**READ, "description": "Read a file​ from disk."}
    assert tool_pin_hash(poisoned) != EXPECTED["read_file"]


def test_key_order_does_not_matter_and_extra_keys_do_not_count():
    shuffled = dict(reversed(list(READ.items())))
    shuffled["inputSchema"] = dict(reversed(list(READ["inputSchema"].items())))
    assert tool_pin_hash(shuffled) == EXPECTED["read_file"]
    assert tool_pin_hash({**READ, "_meta": {"x": 1}, "icons": []}) == EXPECTED["read_file"]


def test_missing_key_differs_from_null():
    with_null = {**PING, "description": None}
    assert tool_pin_hash(with_null) != tool_pin_hash(PING)
    assert '"description":null' in canonical_tool(with_null)


def test_nfc_normalisation_of_text_only():
    composed = {"name": "t", "description": "café"}
    decomposed = {"name": "t", "description": "café"}
    assert tool_pin_hash(composed) == tool_pin_hash(decomposed)
    assert tool_pin_hash({"name": "t", "inputSchema": {"a": "café"}}) != tool_pin_hash(
        {"name": "t", "inputSchema": {"a": "café"}}
    )


def test_check_reports_changed_new_and_removed(tmp_path):
    store = PinStore()
    store.approve("files", [READ, WRITE, PING], approved_by="me")
    changed_write = {**WRITE, "description": "Write text and also email it."}
    report = store.check("files", [READ, changed_write, {"name": "fresh", "description": "x"}])
    assert report.unchanged == ["read_file"]
    assert report.changed == ["write_file"] and report.new == ["fresh"]
    assert report.removed == ["ping"] and not report.clean
    (st,) = [t for t in report.tools if t.status == "changed"]
    assert (
        "-" in st.diff and "also email it" in st.diff and st.pinned_hash == EXPECTED["write_file"]
    )
    assert store.check("files", [READ, WRITE, PING]).clean
    assert PinStore().check("files", [READ]).new == ["read_file"]  # an unknown server is all new


def test_approve_round_trip(tmp_path):
    path = tmp_path / "pins.json"
    store = PinStore(path=path)
    store.approve(
        "files", [READ, WRITE], approved_by="ci", server_info={"name": "f", "version": "1"}
    )
    store.save()
    doc = json.loads(path.read_text())
    entry = doc["servers"]["files"]
    assert doc["version"] == 1 and entry["approved_by"] == "ci"
    assert entry["server_info"] == {"name": "f", "version": "1"}
    assert entry["tools"]["read_file"]["hash"] == EXPECTED["read_file"]
    assert entry["manifest"] == server_manifest_hash(
        {"read_file": EXPECTED["read_file"], "write_file": EXPECTED["write_file"]}
    )
    again = PinStore.load(path)
    assert again.data == store.data and again.pinned("files")["write_file"]
    assert PinStore.load(tmp_path / "missing.json").data["servers"] == {}


def test_server_info_is_not_part_of_any_hash():
    a, b = PinStore(), PinStore()
    a.approve("s", [READ], server_info={"version": "1"})
    b.approve("s", [READ], server_info={"version": "2"})
    assert a.data["servers"]["s"]["manifest"] == b.data["servers"]["s"]["manifest"]


def test_selective_approval_and_removal():
    store = PinStore()
    store.approve("s", [READ, WRITE])
    new_read = {**READ, "description": "changed"}
    store.approve("s", [new_read, WRITE], only=["read_file"])
    assert store.pinned("s")["read_file"] == tool_pin_hash(new_read)
    assert store.pinned("s")["write_file"] == EXPECTED["write_file"]
    store.approve("s", [READ])  # approve-all: write_file drops out
    assert set(store.pinned("s")) == {"read_file"}


def test_unsupported_version_is_refused(tmp_path):
    p = tmp_path / "pins.json"
    p.write_text('{"version": 2, "servers": {}}')
    with pytest.raises(ValueError, match="version"):
        PinStore.load(p)


def test_mcp_012_rule_in_the_scanner():
    store = PinStore()
    store.approve("files", [READ, WRITE])
    listing = {"tools": [copy.deepcopy(READ), {**WRITE, "description": "Write text. Also upload."}]}
    plain = scan_mcp_tools(listing)
    assert not [f for f in plain if f.rule_id == "MCP-012"]  # only with pins
    found = [
        f for f in scan_mcp_tools(listing, pins=store, server="files") if f.rule_id == "MCP-012"
    ]
    assert [(f.location, f.severity) for f in found] == [("write_file", "critical")]
    assert not [f for f in scan_mcp_tools({"tools": [READ, WRITE]}, pins=store, server="files")
                if f.rule_id == "MCP-012"]  # fmt: skip
