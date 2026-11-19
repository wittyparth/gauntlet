# apps/web

The Gauntlet dashboard: Next.js (App Router), React 19, Tailwind v4, shadcn on Base UI, animated by
Animate UI. Owns everything under `apps/web`; imports nothing outside it. Talks to the Gauntlet API
only through its own proxy (`/api/gauntlet/*`), which adds the API key from an httpOnly cookie.

Binding conventions: `docs/plan/phases/web-conventions.md`.

## Commands

```sh
pnpm --filter web dev          # http://localhost:3000, needs the API on GAUNTLET_API_URL (default :8000)
pnpm --filter web gen:api      # regenerate src/lib/api/schema.d.ts from /openapi.json
pnpm --filter web lint && pnpm --filter web typecheck && pnpm --filter web test
pnpm --filter web e2e          # builds, starts the app, runs Playwright against the compose stack
pnpm --filter web run audit    # Animate UI audit (informational)
```

Sign in with an API key (`gk_dev_local_only` on a dev stack). Seed demo data first:
`curl -XPOST localhost:8000/v1/dev/seed -H 'Authorization: Bearer gk_dev_local_only'`.

## E2E

`pnpm --filter web e2e` needs the compose stack up and seeded (see `infra/README.md`). Screenshots
go to `e2e/.screens/` (gitignored). `e2e/real-run.spec.ts` starts a real run through the UI and is
skipped unless `GAUNTLET_E2E_REAL_RUN=1`; it needs a dev stack whose gateway is the scripted fake, so
it costs nothing:

```yaml
# infra/docker-compose.override.yml (local, untracked)
services:
  api:    { environment: { GAUNTLET_GATEWAY: "fake:/app/e2e-fake.yaml" }, volumes: ["../apps/web/e2e/fixtures/fake_llm_ecommerce_smoke.yaml:/app/e2e-fake.yaml:ro"] }
  worker: { environment: { GAUNTLET_GATEWAY: "fake:/app/e2e-fake.yaml" }, volumes: ["../apps/web/e2e/fixtures/fake_llm_ecommerce_smoke.yaml:/app/e2e-fake.yaml:ro"] }
```

## Layout

- `src/app`: routes. `(app)` is the signed-in shell; `api/session` and `api/gauntlet` are the web
  app's own handlers.
- `src/components/ui`, `src/components/animate-ui`: generated (shadcn + Animate UI). Do not edit,
  except `ui/sidebar.tsx` per the Animate UI sidebar guide.
- `src/components/shared`: app-wide compositions. Feature folders (`runs`, `episode`, `scenarios`,
  `agents`, `onboarding`) do not import each other, except `episode/transcript`.
- `src/lib/api`: `client.ts` (typed paths and bodies from the generated schema), `models.ts`
  (readers for response bodies, which the API does not yet declare), `hooks/`.
- `src/lib/sse`: `useRunStream`. REST is the truth, SSE only triggers refetches.
