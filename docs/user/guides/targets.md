# Targets: hosted, wired and black-box

A *target* is the agent under test, described by an agent file (`agent.yaml`).

| Kind | What runs | Use when |
|---|---|---|
| `hosted` | Gauntlet calls the model itself with your system prompt and the world's tools | testing a prompt or model choice |
| `openai_compat`, `wired: true` | your service, an OpenAI-compatible `POST /v1/chat/completions`; it calls the mock world over HTTP with the episode token | testing real agent code |
| black box | a live endpoint you own, probed from outside | scanning a deployed agent; requires ownership verification |

```yaml
label: my-agent
target: {kind: hosted, model: <catalog model id>, system_prompt: "You are a support assistant."}
```

```yaml
label: my-agent-wired
target: {kind: openai_compat, base_url: "http://127.0.0.1:8100/v1", model: my-agent, wired: true}
```

A wired agent must send the header `X-Gauntlet-Episode` and call tools at `{mock_base}/mock/{token}/tools/{tool}`. `apps/dva` is a complete example. For the hosted platform, deployment and API keys see `deploy/README.md` in the repository; ingest, gateway and mining are in the next guides.
