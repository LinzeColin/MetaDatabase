#!/usr/bin/env bash
set -euo pipefail
usage() { echo "usage: deploy/restore.sh [--verify-only | --apply --confirm RESTORE_JOBHUNT] <backup.tar.gz.enc>" >&2; exit 2; }
mode=""
confirm=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --verify-only) mode="verify"; shift ;;
    --apply) mode="apply"; shift ;;
    --confirm) confirm="${2:-}"; shift 2 ;;
    -*) usage ;;
    *) backup="$1"; shift ;;
  esac
done
[[ -n "${backup:-}" && -n "$mode" ]] || usage
cd "$(dirname "$0")/.."
set -a; source .env; set +a
: "${BACKUP_ENCRYPTION_PASSPHRASE:?missing BACKUP_ENCRYPTION_PASSPHRASE}"
[[ -f "$backup" ]] || { echo "backup not found" >&2; exit 1; }
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_ENCRYPTION_PASSPHRASE -in "$backup" \
  | tar -C "$tmp" -xzf -
test -s "$tmp/database.dump"
test -s "$tmp/uploads.tar.gz"
test -s "$tmp/manifest.json"
docker compose exec -T postgres pg_restore --list < "$tmp/database.dump" >/dev/null
if [[ "$mode" == "verify" ]]; then
  echo "backup structure and PostgreSQL archive are readable"
  exit 0
fi
[[ "$confirm" == "RESTORE_JOBHUNT" ]] || { echo "apply mode requires --confirm RESTORE_JOBHUNT" >&2; exit 2; }
pre_restore="$(deploy/backup.sh)"
echo "$pre_restore" > runtime-data/pre-restore-backup.txt
docker compose stop web scheduler worker
docker compose exec -T postgres dropdb -U jobhunt --if-exists jobhunt
docker compose exec -T postgres createdb -U jobhunt jobhunt
docker compose exec -T postgres pg_restore -U jobhunt -d jobhunt --clean --if-exists --no-owner < "$tmp/database.dump"
docker compose run --rm -T web sh -c 'rm -rf /data/uploads/* && tar -C /data/uploads -xzf -' < "$tmp/uploads.tar.gz"
docker compose run --rm web alembic upgrade head
docker compose up -d web scheduler worker
for _ in $(seq 1 60); do
  if curl -fsS "${BASE_URL%/}/readyz" >/dev/null 2>&1; then
    echo "restore completed and HTTPS readback is ready"
    exit 0
  fi
  sleep 3
done
echo "restore applied but application did not become ready; use runtime-data/pre-restore-backup.txt" >&2
exit 1
