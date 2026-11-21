import logging

import pytest
from gauntlet_core.gateway.mcp import UnknownTool, describe, expose_name, split_exposed


def test_prefixing():
    assert expose_name("files", "read_file") == "files__read_file"
    assert describe("files", "Read it.") == "[server: files] Read it."
    assert describe("files", None) == "[server: files]"


def test_tool_name_containing_the_separator_is_renamed(caplog):
    with caplog.at_level(logging.WARNING, logger="gauntlet.gateway.mcp"):
        assert expose_name("crm", "get__customer__data") == "crm__get_customer_data"
    assert "renamed" in caplog.text


def test_split_known_prefix():
    assert split_exposed("files__read_file", {"files", "crm"}) == ("files", "read_file")
    assert split_exposed("a__b__c", {"a"}) == ("a", "b__c")  # only the first separator counts


@pytest.mark.parametrize("name", ["read_file", "nope__read_file", "files__", "__x", ""])
def test_unknown_prefix_is_an_error(name):
    with pytest.raises(UnknownTool):
        split_exposed(name, {"files"})


def test_two_servers_cannot_shadow_each_other():
    assert expose_name("a", "read") != expose_name("b", "read")
