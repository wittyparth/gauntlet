# Gauntlet launch checklist

Works for any single VPS (Oracle Ampere ARM, Hetzner CAX/CX, other Ubuntu or Debian) and for Coolify or Dokploy. Details and per-provider steps are in `deploy/README.md`; this file is the order of operations and the things to verify. Tick each box before announcing.

Files used: `deploy/docker-compose.prod.yml`, `deploy/Caddyfile`, `deploy/bootstrap.sh`, `deploy/backup.sh`, `scripts/demo_smoke.sh`.

## 1. Pre-flight (before you touch the server)

- [ ] `main` is green: Python tests, `ruff check`, `ruff format --check`, `pyright packages`, web `lint`, `typecheck`, `test`, `build`, Playwright e2e.
- [ ] The commit you deploy is tagged (`git tag launch-YYYYMMDD`) so rollback has a name.
- [ ] Host: Ubuntu or Debian, 4 GB RAM minimum (8 GB comfortable), 20 GB disk, amd64 or arm64.
- [ ] Ports 80 TCP, 443 TCP and 443 UDP reachable. Oracle: open them in the VCN security list and on the instance (`bootstrap.sh --open-ports`). Hetzner: allow them in the Cloud Firewall if you attach one.
- [ ] SSH is key-only; the box has a non-root admin user and automatic security updates.
- [ ] Decide what the demo needs:
  - Console, seeded data, policies, smoke test: no model key needed.
  - Live security demo against the Damn Vulnerable Agents: add `dva` to `COMPOSE_PROFILES`, and set `DVA_BRAIN=scripted` for no model spend (the compose default is `llm`, which needs `OPENROUTER_API_KEY`).
- [ ] The public arena is not part of `docker-compose.prod.yml`. The web app proxies `/api/arena/*` to `ARENA_API_URL` (default `http://localhost:8100`), so without a separate arena service the arena page answers 502. Leave it out of a launch, or deploy it as its own service with the settings in section 7 first.

## 2. Secrets

`bootstrap.sh` creates `deploy/.env.prod` (mode 600) from `deploy/.env.prod.example` and fills only empty values, so re-running never rotates a secret.

- [ ] `POSTGRES_PASSWORD`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`: generated, never left at `change-me`.
- [ ] `GAUNTLET_SECRET_KEY` (Fernet key): generated. Back it up with the database; losing it makes stored secrets (alert webhooks, target keys) unreadable.
- [ ] `GAUNTLET_ADMIN_API_KEY`: `gk_` plus at least 20 characters (the bootstrap refuses shorter). Printed once; put it in a password manager.
- [ ] `OPENROUTER_API_KEY`: only if you want live model calls. Exported in the shell when running `sudo -E ./deploy/bootstrap.sh`, never on the command line, never committed.
- [ ] `deploy/.env.prod` is not in git and is backed up separately and securely (it is not in `backup.sh` output).
- [ ] `GAUNTLET_ENV` is fixed to `prod` in the compose file. The application's own default is `dev` (dev API key, `/docs`, `/v1/dev/seed`), so never run the images outside this compose file without setting it. The smoke test checks that `/v1/dev/seed` and `/openapi.json` return 404.
- [ ] No default or example credential remains: the dev key `gk_dev_local_only` and the `gauntlet-dev-only` database password exist only in dev compose and CI. After deploy, `curl -H 'Authorization: Bearer gk_dev_local_only' $URL/v1/projects` must return 401.
- [ ] Note for maintainers: `deploy/.env.prod.example` should list `DVA_BRAIN` and the arena variables (`ARENA_ENABLED`, `ARENA_SECRET`, `ARENA_BRAIN`, `ARENA_DAILY_BUDGET_USD_MICROS`, `ARENA_TRUST_PROXY`) once the arena is deployed. A hook blocks edits to that file from automation, so make the change by hand.

## 3. DNS and TLS

- [ ] An A record (and AAAA if the host has IPv6) for your domain points at the server. Wait for it to resolve (`dig +short gauntlet.example.com`) before the first start: Caddy asks Let's Encrypt on first boot and a wrong record burns rate-limit attempts.
- [ ] `./deploy/bootstrap.sh --domain gauntlet.example.com` sets `DOMAIN` and `GAUNTLET_INSECURE_COOKIE=0`. With `DOMAIN` empty the site is plain HTTP and the cookie is insecure: for a throwaway demo only, the API key travels in clear text.
- [ ] `curl -sI https://gauntlet.example.com/login` shows a valid certificate and `strict-transport-security`.
- [ ] Coolify or Dokploy: remove `caddy` from `COMPOSE_PROFILES`, attach the domain to the `web` service port 3000 (and optionally `api` port 8000 for SDK and CLI clients on a separate domain or `/v1` path). Their proxy issues the certificate. Keep `GAUNTLET_INSECURE_COOKIE=0`.
- [ ] Only 80 and 443 are public. Postgres, Redis, MinIO and the DVA services publish no host ports; confirm with `ss -tlnp` and an external port scan.

## 4. Budget cap

Model spend has three independent stops. Set all three.

- [ ] A monthly spend limit on the OpenRouter key itself (openrouter.ai). This is the hard stop and it also covers the DVA agents, which call the model directly and are not counted by Gauntlet's caps.
- [ ] `GAUNTLET_MAX_RUN_BUDGET_USD_MICROS` (default 5000000, $5 per run) and `GAUNTLET_DAILY_BUDGET_USD` (default 10, rolling 24 hours; 0 disables, so never set 0). Apply with `docker compose -p gauntlet -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod up -d`.
- [ ] Arena, if deployed: `ARENA_DAILY_BUDGET_USD_MICROS` (default $5; the arena closes itself at the cap and reopens next UTC day), per-IP and per-handle limits left at their defaults unless you have a reason.
- [ ] Know the stops: the kill switch (Security page) stops runs in flight; `GAUNTLET_ATTACKS_DISABLED=true` rejects new attack runs; `docker compose ... stop worker` halts all execution.
- [ ] Rehearse once: start a run with a tiny budget and confirm it is clamped or refused.

## 5. Backups

- [ ] Run `deploy/backup.sh -d /var/backups/gauntlet -k 14` once by hand and check the tarball holds `db.dump` and `minio/`.
- [ ] Cron: `17 3 * * * /opt/gauntlet/deploy/backup.sh -d /var/backups/gauntlet -k 14`.
- [ ] Copy that directory off the host (rsync, rclone, object storage). A dump on the same disk is not a backup.
- [ ] Store `deploy/.env.prod` (especially `GAUNTLET_SECRET_KEY`) in the same off-host place, separately encrypted.
- [ ] Restore rehearsal on a scratch host or project: `pg_restore --clean --if-exists -U gauntlet -d gauntlet < db.dump` inside the postgres container, `docker cp` the `minio/` directory back to `/data/gauntlet`, start the stack, run the smoke test. Do this before launch, not after an incident.

## 6. Smoke test

```sh
GAUNTLET_API_KEY=<admin key> BASE_URL=https://gauntlet.example.com scripts/demo_smoke.sh
# with the dva profile, also check the targets from inside the worker:
SMOKE_COMPOSE_PROJECT=gauntlet GAUNTLET_API_KEY=... BASE_URL=... scripts/demo_smoke.sh
```

- [ ] All checks pass. It uses no model calls. It covers health, auth (401 without a key and with a wrong key), prod-mode 404s, the seeded runs, a dry run, console login, 20 console pages and, optionally, the DVA targets.
- [ ] By hand: open the site in a private window, log in with the admin key, open a run, a finding and the policy page. Log out and confirm `/runs` redirects to login.
- [ ] `docker compose -p gauntlet -f deploy/docker-compose.prod.yml ps` shows every service healthy; `docker stats --no-stream` stays inside the memory limits.
- [ ] Logs carry no secrets: `docker compose ... logs api worker | grep -ci 'gk_\|sk-or'` returns 0.

## 7. Arena (only if you deploy it)

The arena has no accounts and is public by design, so it carries its own limits.

- [ ] `ARENA_ENABLED=true`, `ARENA_SECRET` set to a random value (the service refuses to start enabled without it), `ARENA_DATABASE_URL`, `ARENA_REDIS_URL`.
- [ ] `ARENA_BRAIN=llm` uses a catalog model and costs money; `scripted` is free. Budget as in section 4.
- [ ] `ARENA_TRUST_PROXY=true` only when every request reaches it through a proxy that overwrites `X-Forwarded-For` (Caddy does by default). Without it every visitor shares the web container's address and the per-IP limit becomes global.
- [ ] The arena listens on loopback or the compose network only. Public traffic reaches it through the web app's `/api/arena` proxy.

## 8. Rollback

- [ ] Before every update: run `deploy/backup.sh`, and note the running commit (`git -C /opt/gauntlet rev-parse --short HEAD`).
- [ ] Code rollback (no schema change in the release): `git -C /opt/gauntlet checkout <previous tag>` then `sudo ./deploy/bootstrap.sh`. It rebuilds and restarts; secrets are untouched.
- [ ] Release with a migration: migrations only move forward and run on every start. Roll back by restoring the pre-update backup (section 5) after checking out the previous tag. Take the backup first, always.
- [ ] Stack down but data kept: `docker compose -p gauntlet -f deploy/docker-compose.prod.yml down` (no `-v`). `down -v` deletes the database and the bucket.
- [ ] Emergency stop of spend: engage the kill switch, or set `GAUNTLET_ATTACKS_DISABLED=true` and re-apply, or `stop worker dva dva-sql dva-email`.

## Known and accepted

- The policy engine defaults to `fail: open` per policy (a bug in the engine allows the call and records `guard_error`). Policies that guard something irreversible should set `fail: closed`; the arena levels already do.
- Caddy forwards `/v1/*` to the API with no rate limit of its own; abuse control is the API key plus the budget caps. Put a rate limit at the host or CDN if the API is exposed to the open internet.
- The target and webhook SSRF guard resolves a hostname and then lets the HTTP client resolve it again; a DNS answer that flips between the two lookups is not pinned. Exposure needs control of a verified domain, and the private-address check runs again on every request.
- No CSP header on the console yet; the console renders no user HTML and the session cookie is `HttpOnly`, `SameSite=Lax`.
