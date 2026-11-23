# Quickstart: first report in 5 minutes

Needs Python 3.12 and [uv](https://docs.astral.sh/uv/). No API key and no model call: a scripted fake LLM answers, so the run is deterministic and free.

```sh check
$ uv sync
$ uv run gauntlet validate docs/user/examples/tinyshop
$ uv run gauntlet run docs/user/examples/tinyshop --target docs/user/examples/agent.yaml --suite smoke --fake-llm docs/user/examples/fake_llm_smoke.yaml --out runs/quickstart
$ uv run gauntlet report runs/quickstart
```

What you get: a pack (`docs/user/examples/tinyshop`: a tiny shop world, a policy and two scenarios) was validated and run against a hosted agent file. One scenario passes (the agent looks the order up and answers), one fails (the agent refuses to cancel an order it should cancel). `runs/quickstart/` holds the report, journals and cassettes; every episode can be replayed.

Exit codes of `gauntlet run`: 0 completed, 1 `--fail-under` not met, 2 usage or validation error, 3 platform failure, 130 interrupted (use `--resume`).

## Next

- Validate the full e-commerce pack against the Damn Vulnerable Agent: `uv run gauntlet validate packs/ecommerce`. The DVA (`apps/dva`) is a deliberately flawed agent; its scripted brain (`DVA_BRAIN=scripted`) is deterministic and needs no model. Never expose it publicly.
- Run a real model: pick one from the catalog (`gauntlet_core.llm.catalog`, cheap models only), set the provider key in your environment and pass `--budget-usd`. Live runs spend money; the cap is enforced.
- Start the platform and browse results: see the [hosted guide](guides/targets.md) and `deploy/README.md` in the repository.
