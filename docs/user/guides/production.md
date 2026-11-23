# Production ingest and mining

Send real conversations (OpenTelemetry spans) to your Gauntlet server to evaluate production behaviour, then mine failures into new scenarios.

1. **Ingest.** Point your OpenTelemetry exporter at the server's ingest endpoint with an API key. Personal data is redacted with workspace-scoped keyed tokens before storage (linkable inside a workspace, not across; rotating the key breaks linkage by design). Imported conversations are stored as `purpose=import` runs without effects and hidden from run lists unless asked for.
2. **Evaluate.** `POST /v1/production/conversations/{id}/evaluate` runs checks and rubrics over a conversation. World-state checks report `undetermined` because an imported conversation has no world.
3. **Mine.** `POST /v1/production/mine` clusters failing conversations into candidates; mining requires a budget. Review `GET /v1/production/candidates`, then `convert` a candidate into a scenario (conversion fails closed) or `dismiss` it.

Everything is in the [REST reference](../reference/api.md); retention and budget settings are in `deploy/README.md`.
