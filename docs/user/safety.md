# Safety and responsible use

- **Only test what you own or may test.** Scanners and attack libraries are for your agents, your MCP servers and your own infrastructure, or targets whose owner authorised you in writing. Black-box targets are verified (domain ownership) before attacks run.
- **Everything is fake by default.** Worlds contain synthetic data and handlers; secrets in packs and in the Damn Vulnerable Agent are fake. Never put real credentials or personal data in a pack.
- **No surprise spend.** Live model runs are opt-in, need a provider key you set yourself, use cheap catalog models, and stop at the budget cap (`--budget-usd`, server caps `GAUNTLET_MAX_RUN_BUDGET_USD_MICROS` and `GAUNTLET_DAILY_BUDGET_USD`). The MCP server's `create_run` needs `confirm=true` and a budget within `GAUNTLET_MCP_MAX_BUDGET_USD` (default 1.0).
- **Offline by default.** Webhooks, email, docs deploy and any other network feature are off until you configure them. Nothing phones home.
- **Dangerous attack categories** are marked in the [taxonomy](reference/taxonomy.md) and need explicit opt-in.
- **Reporting a vulnerability in Gauntlet itself:** open a private security advisory on the repository rather than a public issue.
