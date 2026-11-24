#!/usr/bin/env bash
# End-to-end check of a deployed Gauntlet stack. NO model calls, no spend: it reads the data that
# `python -m gauntlet_server.demo seed` created (two finished runs executed with a scripted model),
# does a dry-run of a new run, and walks the console pages through the same login a user does.
#
#   GAUNTLET_API_KEY=gk_... BASE_URL=https://gauntlet.example.com scripts/demo_smoke.sh
#
# Env: BASE_URL (default http://localhost), GAUNTLET_API_KEY (required),
#      SMOKE_COMPOSE_PROJECT (optional compose project name: also checks the DVA targets from
#      inside the worker container), SMOKE_DEV=1 (skip the prod-mode 404 checks).
set -u
BASE="${BASE_URL:-http://localhost}"; BASE="${BASE%/}"
KEY="${GAUNTLET_API_KEY:-}"
[ -n "$KEY" ] || { echo "set GAUNTLET_API_KEY" >&2; exit 2; }
JAR="$(mktemp)"; trap 'rm -f "$JAR"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); printf '  ok    %s\n' "$1"; }
bad() { fail=$((fail+1)); printf '  FAIL  %s\n' "$1" >&2; }
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$@"; }
get()  { curl -s --max-time 30 -H "Authorization: Bearer $KEY" "$BASE$1"; }
expect() { # name expected actual
  if [ "$3" = "$2" ]; then ok "$1"; else bad "$1 (expected $2, got $3)"; fi; }
jq_() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)" 2>/dev/null; }

echo "Gauntlet smoke: $BASE"
echo "health and auth"
expect "GET /healthz" 200 "$(code "$BASE/healthz")"
expect "unauthenticated /v1/projects is refused" 401 "$(code "$BASE/v1/projects")"
expect "bad key is refused" 401 "$(code -H 'Authorization: Bearer gk_wrong' "$BASE/v1/projects")"
expect "admin key accepted" 200 "$(code -H "Authorization: Bearer $KEY" "$BASE/v1/projects")"
if [ -z "${SMOKE_DEV:-}" ]; then
  expect "dev seed route absent (prod mode)" 404 "$(code -X POST -H "Authorization: Bearer $KEY" "$BASE/v1/dev/seed")"
  expect "openapi not published (prod mode)" 404 "$(code "$BASE/openapi.json")"
fi

echo "seeded demo data"
run="$(get /v1/runs/run_demo)"
expect "run_demo finished" "done" "$(echo "$run" | jq_ "d['status']")"
rep="$(get /v1/runs/run_demo/report)"
expect "run_demo judged 10 episodes" 10 "$(echo "$rep" | jq_ "d['counted']")"
eps="$(get '/v1/runs/run_demo/episodes?limit=50')"
failed="$(echo "$eps" | jq_ "next((e['id'] for e in (d.get('items') or d) if e.get('outcome')=='failed'), '')")"
if [ -n "$failed" ]; then ok "a failing episode exists ($failed)"; else bad "no failing episode in run_demo"; fi
expect "run_demo_b (compare partner) finished" "done" "$(get /v1/runs/run_demo_b | jq_ "d['status']")"
expect "episode detail loads" 200 "$(code -H "Authorization: Bearer $KEY" "$BASE/v1/episodes/${failed:-none}")"
expect "demo policy present" 200 "$(code -H "Authorization: Bearer $KEY" "$BASE/v1/policies/pol_demo")"
expect "scorecard loads" 200 "$(code -H "Authorization: Bearer $KEY" "$BASE/v1/agents/agt_demo/versions/agv_demo/scorecard")"
dry="$(curl -s --max-time 30 -X POST -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"suite_id":"ecommerce_smoke","agent_version_id":"agv_demo","budget_usd_micros":1000000}' "$BASE/v1/runs?dry_run=true")"
expect "dry-run of a new run validates (no spend)" True "$(echo "$dry" | jq_ "d['valid']")"

echo "console pages (after login)"
lc="$(curl -s -o /dev/null -w '%{http_code}' -c "$JAR" -X POST -H 'Content-Type: application/json' \
  -d "{\"api_key\":\"$KEY\"}" "$BASE/api/session")"
expect "login with the API key" 200 "$lc"
expect "login with a wrong key is refused" 401 "$(code -X POST -H 'Content-Type: application/json' -d '{"api_key":"gk_wrong"}' "$BASE/api/session")"
for p in / /runs /runs/run_demo /runs/run_demo/report /runs/run_demo/compare "/episodes/${failed:-ep_demo_6}" \
         /findings /scenarios /agents /agents/agt_demo /agents/agt_demo/scorecard /security \
         /security/campaigns/new /security/audit /gateway /gateway/policies /gateway/policies/pol_demo \
         /gateway/approvals /review /rubrics /settings/models; do
  expect "page $p" 200 "$(code -b "$JAR" "$BASE$p")"
done

if [ -n "${SMOKE_COMPOSE_PROJECT:-}" ]; then
  echo "DVA targets (from the worker)"
  wc="$(docker ps -q --filter "label=com.docker.compose.project=$SMOKE_COMPOSE_PROJECT" \
    --filter label=com.docker.compose.service=worker | head -1)"
  for h in dva:8100 dva-sql:8101 dva-email:8102; do
    if [ -n "$wc" ] && docker exec "$wc" python -c \
      "import urllib.request as u; u.urlopen('http://$h/healthz', timeout=5)" >/dev/null 2>&1; then
      ok "$h reachable"; else bad "$h unreachable"; fi
  done
fi

echo "---"; echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
