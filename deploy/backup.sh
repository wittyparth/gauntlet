#!/usr/bin/env bash
# Back up Postgres (pg_dump, custom format) and the MinIO bucket to a local directory, then prune.
#
#   deploy/backup.sh [-d DIR] [-k N] [-p PROJECT]
#     -d DIR      destination (default deploy/backups next to this script) [BACKUP_DIR]
#     -k N        keep the newest N backups (default 7) [BACKUP_KEEP]
#     -p PROJECT  compose project name (default gauntlet) [COMPOSE_PROJECT]
# Reads no secrets: it execs into the running containers, which already hold them. Copy DIR off
# the host (rsync, rclone, object storage) for a real backup; a dump on the same disk is not one.
# Restore: pg_restore --clean --if-exists -U gauntlet -d gauntlet < db.dump  (in the postgres
# container); docker cp the minio/ directory back into the minio container at /data/gauntlet.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
DEST="${BACKUP_DIR:-$here/backups}"; KEEP="${BACKUP_KEEP:-7}"; PROJECT="${COMPOSE_PROJECT:-gauntlet}"
while getopts "d:k:p:" o; do
  case "$o" in d) DEST="$OPTARG";; k) KEEP="$OPTARG";; p) PROJECT="$OPTARG";; *) exit 2;; esac
done
cid() {
  docker ps -q --filter "label=com.docker.compose.project=$PROJECT" \
    --filter "label=com.docker.compose.service=$1" | head -1
}
pg="$(cid postgres)"; mn="$(cid minio)"
if [ -z "$pg" ] || [ -z "$mn" ]; then
  echo "postgres/minio containers of project '$PROJECT' are not running" >&2; exit 1
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"; out="$DEST/$stamp"
mkdir -p "$out/minio"; chmod 700 "$DEST"
echo "postgres -> $out/db.dump"
docker exec "$pg" pg_dump -U gauntlet -d gauntlet -Fc -f /tmp/gauntlet.dump
docker cp "$pg:/tmp/gauntlet.dump" "$out/db.dump"
docker exec "$pg" rm -f /tmp/gauntlet.dump
echo "minio -> $out/minio"
# The bucket is a directory inside the minio container's data volume.
docker cp "$mn:/data/gauntlet/." "$out/minio/" || echo "(bucket empty)"
tar -C "$DEST" -czf "$out.tar.gz" "$stamp"
rm -rf "$out"
chmod 600 "$out.tar.gz"
# Retention: the newest KEEP archives survive.
# shellcheck disable=SC2012
ls -1t "$DEST"/*.tar.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs rm -f
echo "done: $out.tar.gz ($(ls -1 "$DEST"/*.tar.gz | wc -l | tr -d ' ') kept, max $KEEP)"
