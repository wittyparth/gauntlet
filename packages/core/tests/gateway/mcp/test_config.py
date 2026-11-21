import pytest
from gauntlet_core.gateway.mcp import McpGatewayConfig
from pydantic import ValidationError

VALID = """
policy: policy.yaml
pins: pins.json
on_pin_mismatch: block
on_unpinned: warn
scan:
  block_at: medium
risk_overrides: {"files__write_file": destructive}
servers:
  - name: files
    transport: stdio
    command: ["npx", "some-mcp-server"]
    env: {ROOT_DIR: /srv/data, TOKEN: "${FILES_TOKEN}"}
    trust: untrusted
    allow_tools: ["read_*"]
    deny_tools: ["delete_*"]
    scopes: {max_risk: write}
  - name: crm
    transport: http
    url: https://crm.example.test/mcp
    headers: {Authorization: "Bearer ${CRM_TOKEN}"}
    trust: trusted
"""


def load(tmp_path, text):
    p = tmp_path / "gateway.yaml"
    p.write_text(text)
    return McpGatewayConfig.load(p)


def test_valid_config_and_defaults(tmp_path):
    cfg = load(tmp_path, VALID)
    assert [s.name for s in cfg.servers] == ["files", "crm"]
    assert cfg.on_unpinned == "warn" and cfg.on_pin_mismatch == "block"
    assert cfg.scan.block_at == "medium" and cfg.risk_overrides == {
        "files__write_file": "destructive"
    }
    files = cfg.server("files")
    assert files.allow_tools == ["read_*"] and files.scopes.max_risk == "write"
    assert cfg.server("crm").trust == "trusted"
    assert cfg.pins == str(tmp_path / "pins.json") and cfg.policy == str(tmp_path / "policy.yaml")
    minimal = load(tmp_path, "servers:\n  - {name: a, transport: http, url: 'http://x'}\n")
    assert minimal.server("a").trust == "untrusted"  # the safe default
    assert (minimal.on_pin_mismatch, minimal.on_unpinned) == ("block", "block")


def test_env_and_header_interpolation_only_for_the_named_keys(tmp_path):
    cfg = load(tmp_path, VALID)
    env = {"PATH": "/bin", "FILES_TOKEN": "tok-123", "CRM_TOKEN": "crm-abc", "SECRET_OTHER": "x"}
    assert cfg.server("files").resolved_env(env) == {
        "PATH": "/bin",
        "ROOT_DIR": "/srv/data",
        "TOKEN": "tok-123",
    }  # nothing else from the gateway's environment is passed on
    assert cfg.server("crm").resolved_headers(env) == {"Authorization": "Bearer crm-abc"}
    # the loaded config keeps the placeholders: secrets are not in repr, dumps or logs
    assert "tok-123" not in cfg.model_dump_json() and "${CRM_TOKEN}" in repr(cfg)
    with pytest.raises(ValueError, match="CRM_TOKEN"):
        cfg.server("crm").resolved_headers({})


def test_unknown_keys_are_rejected(tmp_path):
    with pytest.raises(ValidationError, match="surprise"):
        load(tmp_path, VALID + "surprise: 1\n")
    bad = "servers:\n  - {name: a, transport: http, url: 'http://x', colour: red}\n"
    with pytest.raises(ValidationError):
        load(tmp_path, bad)


@pytest.mark.parametrize("name", ["Files", "1files", "a-b", "a" * 32, ""])
def test_bad_server_names(tmp_path, name):
    with pytest.raises(ValidationError, match="name"):
        load(tmp_path, f"servers:\n  - {{name: '{name}', transport: http, url: 'http://x'}}\n")


def test_transport_fields_and_duplicates(tmp_path):
    with pytest.raises(ValidationError, match="command"):
        load(tmp_path, "servers:\n  - {name: a, transport: stdio}\n")
    with pytest.raises(ValidationError, match="url"):
        load(tmp_path, "servers:\n  - {name: a, transport: http}\n")
    dup = (
        "servers:\n  - {name: a, transport: http, url: 'x'}\n"
        "  - {name: a, transport: http, url: 'y'}\n"
    )
    with pytest.raises(ValidationError, match="unique"):
        load(tmp_path, dup)
    with pytest.raises(ValidationError):
        load(tmp_path, "servers: []\n")
