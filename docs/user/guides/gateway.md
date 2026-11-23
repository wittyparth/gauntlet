# Gateway and MCP gateway

The **gateway** enforces a published policy at runtime: each tool call is allowed, denied, or held for approval, using policy rules, an injection-classifier detector and taint rules. Decisions are recorded (`/v1/gateway/decisions`) and approvals are decided through `/v1/gateway/approvals`.

The **MCP gateway** sits between an agent and its upstream MCP servers:

```sh
gauntlet mcp pin --config gateway.yaml          # record tool definitions (never calls a tool)
gauntlet mcp diff --config gateway.yaml         # show changes since the pin
gauntlet mcp-gateway serve --config gateway.yaml --decisions decisions.jsonl
gauntlet mcp-gateway serve --config gateway.yaml --http 127.0.0.1:8770
```

Pinned definitions defeat "rug pull" changes: a tool whose description or schema changed is hidden until a person re-approves it. Compile policy text into rules with `gauntlet policy compile`, inspect with `gauntlet policy check`.

## Driving Gauntlet from a coding agent (`gauntlet-mcp`)

The separate `gauntlet-mcp` server exposes the platform to coding agents over stdio (`gauntlet-mcp`) or streamable HTTP (`gauntlet-mcp --http`). It reads `GAUNTLET_API_URL` and `GAUNTLET_API_KEY` (or a per-request `Authorization: Bearer` header over HTTP).

Tools: `list_agents`, `list_runs`, `get_run_report`, `get_episode`, `list_findings`, `get_finding`, `generate_scenarios`, `compare_runs`, `list_policies`, `create_run`. Only `create_run` writes: it requires `confirm=true` and a `budget_usd` up to `GAUNTLET_MCP_MAX_BUDGET_USD` (default 1.0). Nothing deletes, edits a policy or publishes. Every result is capped at `GAUNTLET_MCP_MAX_BYTES` (default 20000) with a truncation marker, and credential-looking fields are removed.
