from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from cli_helpers import FIXTURES, invoke

SERVER = FIXTURES / "mcp_server.py"
CORE_FIX = Path(__file__).resolve().parents[2] / "core" / "tests" / "fixtures" / "mcp"


def stdio_cmd(called: Path, *extra: str) -> str:
    return f"{sys.executable} {SERVER} stdio --called {called} {' '.join(extra)}"


def test_tools_file_poisoned_exits_1_and_clean_exits_0(runner):
    res = invoke(runner, ["scan", "mcp", "--tools-file", str(CORE_FIX / "poisoned.json")])
    assert res.exit_code == 1
    assert "MCP-001" in res.stdout and "MCP-002" in res.stdout
    assert (
        invoke(runner, ["scan", "mcp", "--tools-file", str(CORE_FIX / "clean.json")]).exit_code == 0
    )


def test_fail_on_threshold_and_formats(runner):
    f = str(CORE_FIX / "shadowing.json")
    assert (
        invoke(runner, ["scan", "mcp", "--tools-file", f, "--fail-on", "critical"]).exit_code == 0
    )
    assert invoke(runner, ["scan", "mcp", "--tools-file", f, "--fail-on", "medium"]).exit_code == 1
    res = invoke(runner, ["scan", "mcp", "--tools-file", f, "--format", "sarif"])
    assert json.loads(res.stdout)["version"] == "2.1.0"
    res = invoke(runner, ["scan", "mcp", "--tools-file", f, "--format", "json"])
    assert json.loads(res.stdout)[0]["rule_id"].startswith("MCP-")


def test_usage_errors_exit_2(runner):
    assert invoke(runner, ["scan", "mcp"]).exit_code == 2
    both = ["scan", "mcp", "--url", "http://x", "--tools-file", "y"]
    assert invoke(runner, both).exit_code == 2
    assert invoke(runner, ["scan", "mcp", "--tools-file", "/nonexistent.json"]).exit_code == 2


def test_stdio_poisoned_server_exits_1_and_never_calls_a_tool(runner, tmp_path):
    called = tmp_path / "called.log"
    res = invoke(runner, ["scan", "mcp", "--stdio", stdio_cmd(called, "--poisoned")])
    assert res.exit_code == 1 and "MCP-001" in res.stdout
    assert not called.exists()  # no tools/call was ever sent


def test_stdio_clean_server_exits_0(runner, tmp_path):
    called = tmp_path / "called.log"
    res = invoke(runner, ["scan", "mcp", "--stdio", stdio_cmd(called), "--fail-on", "critical"])
    assert res.exit_code == 0 and not called.exists()


def test_connection_failure_exits_2(runner):
    res = invoke(
        runner, ["scan", "mcp", "--stdio", "definitely-not-a-command-xyz", "--timeout", "5"]
    )
    assert res.exit_code == 2
    res = invoke(runner, ["scan", "mcp", "--url", "http://127.0.0.1:9/mcp", "--timeout", "5"])
    assert res.exit_code == 2


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def http_server(tmp_path):
    port, called = _free_port(), tmp_path / "called.log"
    proc = subprocess.Popen(
        [
            sys.executable,
            str(SERVER),
            "http",
            "--port",
            str(port),
            "--poisoned",
            "--called",
            str(called),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(100):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}/mcp", called
    proc.terminate()
    proc.wait(timeout=10)


def test_http_server_scan_flags_poison_and_loopback_unauthenticated(runner, http_server):
    url, called = http_server
    res = invoke(runner, ["scan", "mcp", "--url", url, "--format", "json"])
    assert res.exit_code == 1
    rules = {f["rule_id"]: f["severity"] for f in json.loads(res.stdout)}
    assert rules["MCP-001"] == "critical" and rules["MCP-009"] == "low"
    assert not called.exists()
