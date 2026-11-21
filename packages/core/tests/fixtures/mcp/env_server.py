"""A stdio MCP server that reports what environment it was started with.

env_server.py stdio
"""

from __future__ import annotations

import hashlib
import json
import os

from mcp.server import MCPServer

server = MCPServer("env-fixture")


@server.tool()
def env_report() -> str:
    """Report the names of the environment variables this process received."""
    token = os.environ.get("TOKEN", "")
    return json.dumps(
        {"keys": sorted(os.environ), "token_sha": hashlib.sha256(token.encode()).hexdigest()}
    )


if __name__ == "__main__":
    server.run("stdio")
