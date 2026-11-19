# Damn Vulnerable Agent (DVA)

A deliberately flawed e-commerce support agent for testing Gauntlet. **It is intentionally vulnerable. It binds to `127.0.0.1` by default. Never expose it publicly and never give it real credentials or real data.** See [CATALOG.md](CATALOG.md) for the 19 planted flaws.

Two variants:

- **Wired**: this app, an OpenAI-compatible `POST /v1/chat/completions` that calls the Gauntlet mock world over HTTP (`{mock_base}/mock/{token}/tools/{tool}`). Header `X-Gauntlet-Episode` is required; `X-Gauntlet-Mock-Base` overrides `GAUNTLET_MOCK_BASE`.
- **Hosted**: `hosted.yaml`, an agent file whose system prompt carries the prompt-type flaws. Gauntlet runs it itself. Regenerate with `uv run python -m dva.export_hosted`.

## Run

```bash
uv sync
DVA_BRAIN=scripted uv run python -m dva.app          # deterministic, no model
DVA_FLAWS=F01,F13 uv run python -m dva.app           # only some flaws (default: all, empty: none)
```

| Env | Default | Meaning |
|---|---|---|
| `DVA_BRAIN` | `llm` | `llm` (LiteLLM tool loop, needs `OPENROUTER_API_KEY`) or `scripted` (CI) |
| `DVA_MODEL` | `openrouter/deepseek/deepseek-v4-flash` | model of the `llm` brain |
| `DVA_FLAWS` | `all` | comma list of flaw ids, or empty for none |
| `GAUNTLET_MOCK_BASE` | `http://127.0.0.1:8000` | where the mock world lives |
| `DVA_HOST` / `DVA_PORT` | `127.0.0.1` / `8100` | bind address |

## Use it

Local CLI against the hosted variant (a live model, asks for budget):

```bash
uv run gauntlet run packs/ecommerce --target apps/dva/hosted.yaml --suite smoke --budget-usd 0.5
```

Local CLI against the wired app (start it first, then point an agent file at it):

```yaml
label: dva-wired
target: {kind: openai_compat, base_url: "http://127.0.0.1:8100/v1", model: dva, wired: true}
```

Compose (needs the api service of P1-9 for the mock world):

```bash
docker compose -f infra/docker-compose.yml --profile dva up -d --build
```

## Tests

`uv run pytest apps/dva -q` proves every Phase 1 flaw: with the flaw on, the scripted episode fails a named check of the ecommerce pack; with `DVA_FLAWS=` it passes. No live model is called.
