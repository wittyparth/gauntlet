#!/usr/bin/env bash
# Gauntlet one-shot installer for a fresh Ubuntu/Debian VPS (amd64 or arm64). Idempotent: re-run it
# to update the code and re-apply the stack; existing secrets in deploy/.env.prod are never replaced.
#
#   sudo REPO_URL=<git url> bash bootstrap.sh            # on a bare box: clones into /opt/gauntlet
#   sudo ./deploy/bootstrap.sh [--domain gauntlet.example.com] [--open-ports]   # from a checkout
#
# Options (or the env var in brackets):
#   --domain NAME   public DNS name for automatic HTTPS [DOMAIN]; omit for a plain-HTTP IP demo
#   --dir PATH      where to clone when not run from a checkout [INSTALL_DIR, /opt/gauntlet]
#   --repo URL      git remote to clone [REPO_URL]
#   --branch NAME   branch to deploy [BRANCH, main]
#   --open-ports    also open 80/443 in the instance iptables (Oracle Cloud images block them)
#   --no-seed       skip loading the demo data
#   --no-swap       do not create a swap file on small hosts
#   -y, --yes       never prompt; use env vars and generated values
# OPENROUTER_API_KEY is read from the environment if exported (never from the command line); it is
# only written to deploy/.env.prod, which is chmod 600.
set -euo pipefail

DOMAIN="${DOMAIN:-}"; INSTALL_DIR="${INSTALL_DIR:-/opt/gauntlet}"; REPO_URL="${REPO_URL:-}"
BRANCH="${BRANCH:-main}"; OPEN_PORTS=0; SEED=1; SWAP=1; YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    --repo) REPO_URL="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --open-ports) OPEN_PORTS=1; shift ;;
    --no-seed) SEED=0; shift ;;
    --no-swap) SWAP=0; shift ;;
    -y|--yes) YES=1; shift ;;
    -h|--help) sed -n 2,19p "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

say() { printf '\n==> %s\n' "$*"; }
[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)" >&2; exit 1; }
# shellcheck disable=SC1091
. /etc/os-release 2>/dev/null || true
case "${ID:-}${ID_LIKE:-}" in *debian*|*ubuntu*) ;; *) echo "warning: tested on Debian/Ubuntu only" >&2 ;; esac
interactive() { [ "$YES" -eq 0 ] && [ -t 0 ]; }

# --- swap: building the web and python images wants more than 2 GB on small boxes
mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
if [ "$SWAP" -eq 1 ] && [ "$mem_kb" -lt 6000000 ] && [ "$(swapon --noheadings | wc -l)" -eq 0 ]; then
  say "creating a 2 GB swap file (host has under 6 GB RAM)"
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# --- docker, git, openssl
need=()
command -v git >/dev/null || need+=(git)
command -v openssl >/dev/null || need+=(openssl)
command -v curl >/dev/null || need+=(curl ca-certificates)
if [ ${#need[@]} -gt 0 ]; then apt-get update -qq && apt-get install -y -qq "${need[@]}" >/dev/null; fi
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  say "installing Docker (get.docker.com)"
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null 2>&1 || true

# --- code: use the checkout this script lives in, else clone/pull INSTALL_DIR
here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$here" ] && [ -f "$here/docker-compose.prod.yml" ]; then
  ROOT="$(cd "$here/.." && pwd)"
  say "using the checkout at $ROOT"
  if [ -d "$ROOT/.git" ]; then git -C "$ROOT" pull --ff-only || echo "(pull skipped; deploying the checkout as is)"; fi
else
  [ -n "$REPO_URL" ] || { echo "set REPO_URL (or --repo) to clone from" >&2; exit 1; }
  ROOT="$INSTALL_DIR"
  if [ -d "$ROOT/.git" ]; then
    say "updating $ROOT"
    git -C "$ROOT" fetch -q origin "$BRANCH" && git -C "$ROOT" checkout -q "$BRANCH" && git -C "$ROOT" pull -q --ff-only
  else
    say "cloning into $ROOT"
    git clone -q --branch "$BRANCH" "$REPO_URL" "$ROOT"
  fi
fi
cd "$ROOT/deploy"

# --- env file: create from the example, fill only what is empty, never overwrite a value
ENVF=".env.prod"; first=0
if [ ! -f "$ENVF" ]; then cp .env.prod.example "$ENVF"; first=1; fi
chmod 600 "$ENVF"
get() { grep -E "^$1=" "$ENVF" | head -1 | cut -d= -f2- || true; }
set_var() {
  local v; v="$(printf '%s' "$2" | sed 's/[\/&|]/\\&/g')"
  if grep -qE "^$1=" "$ENVF"; then
    sed -i.bak "s|^$1=.*|$1=$v|" "$ENVF" && rm -f "$ENVF.bak"
  else
    echo "$1=$2" >> "$ENVF"
  fi
}
fill() { # fill NAME VALUE: only when empty or still an example placeholder; returns 0 if it set it
  local cur; cur="$(get "$1")"
  if [ -z "$cur" ] || [ "$cur" = "change-me" ] || [ "$cur" = "change-me-too" ]; then
    set_var "$1" "$2"; return 0
  fi
  return 1
}
newkey=""
fill POSTGRES_PASSWORD "$(openssl rand -hex 24)" || true
fill MINIO_ROOT_PASSWORD "$(openssl rand -hex 24)" || true
fill GAUNTLET_SECRET_KEY "$(openssl rand -base64 32 | tr '+/' '-_')" || true   # a valid Fernet key
if fill GAUNTLET_ADMIN_API_KEY "gk_$(openssl rand -hex 16)"; then newkey="$(get GAUNTLET_ADMIN_API_KEY)"; fi

if [ -n "$DOMAIN" ]; then
  set_var DOMAIN "$DOMAIN"; set_var GAUNTLET_INSECURE_COOKIE 0
elif [ -z "$(get DOMAIN)" ]; then
  if interactive && [ "$first" -eq 1 ]; then
    read -r -p "Domain for HTTPS (blank = plain HTTP on this server's IP): " d || d=""
    if [ -n "$d" ]; then set_var DOMAIN "$d"; set_var GAUNTLET_INSECURE_COOKIE 0; fi
  fi
  if [ -z "$(get DOMAIN)" ]; then set_var GAUNTLET_INSECURE_COOKIE 1; fi
fi
if [ -n "${OPENROUTER_API_KEY:-}" ]; then
  set_var OPENROUTER_API_KEY "$OPENROUTER_API_KEY"
elif interactive && [ "$first" -eq 1 ]; then
  read -r -s -p "OPENROUTER_API_KEY (blank = no live model calls; the scripted demo still works): " k || k=""
  echo
  if [ -n "$k" ]; then set_var OPENROUTER_API_KEY "$k"; fi
fi

# --- host firewall (Oracle Cloud images ship iptables rules that reject all but ssh)
if [ "$OPEN_PORTS" -eq 1 ]; then
  say "opening 80/443 in iptables"
  for spec in "tcp 80" "tcp 443" "udp 443"; do
    read -r proto port <<<"$spec"
    iptables -C INPUT -p "$proto" --dport "$port" -j ACCEPT 2>/dev/null ||
      iptables -I INPUT -p "$proto" --dport "$port" -j ACCEPT
  done
  if command -v netfilter-persistent >/dev/null; then
    netfilter-persistent save >/dev/null 2>&1
  else
    echo "note: apt install iptables-persistent to keep these rules across reboots"
  fi
fi
if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw allow 443/udp >/dev/null
fi

# --- start
say "building and starting the stack (the first build takes several minutes)"
DC=(docker compose -p gauntlet -f docker-compose.prod.yml --env-file "$ENVF")
"${DC[@]}" up -d --build --wait --remove-orphans
if [ "$SEED" -eq 1 ]; then
  say "loading the demo data (scripted, no model calls)"
  "${DC[@]}" exec -T api python -m gauntlet_server.demo seed >/dev/null
fi

host="$(get DOMAIN)"
if [ -n "$host" ]; then
  url="https://$host"
else
  url="http://$(curl -fsS -m 5 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')"
fi
say "Gauntlet is up: $url"
if [ -n "$newkey" ]; then
  echo "Admin API key (shown once here; it is also in $ROOT/deploy/$ENVF, mode 600):"
  echo "  $newkey"
else
  echo "Admin API key: see GAUNTLET_ADMIN_API_KEY in $ROOT/deploy/$ENVF"
fi
echo "Verify:  GAUNTLET_API_KEY=<key> BASE_URL=$url $ROOT/scripts/demo_smoke.sh"
echo "Backups: $ROOT/deploy/backup.sh   (cron example in deploy/README.md)"
