# Scanning an MCP server

`gauntlet scan mcp` connects read-only (`initialize`, `tools/list`, `resources/list`, `prompts/list`; it never calls a tool) and reports risky tool definitions: prompt injection in descriptions, shadowing, over-broad schemas, destructive hints.

```sh
gauntlet scan mcp --stdio "python my_server.py" --fail-on high
```

Only scan servers you own or are authorised to test. For running the platform's own MCP server see the [gateway guide](gateway.md).
