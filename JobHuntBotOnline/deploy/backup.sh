#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
: "${BACKUP_ENCRYPTION_PASSPHRASE:?missing BACKUP_ENCRYPTION_PASSPHRASE}"
mkdir -p runtime-data/backups
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

docker compose exec -T postgres pg_dump -U jobhunt -d jobhunt --format=custom > "$tmp/database.dump"
docker compose exec -T web tar -C /data/uploads -czf - . > "$tmp/uploads.tar.gz"
docker compose exec -T web alembic current > "$tmp/alembic-current.txt"
image_id="$(docker compose images -q web | head -1 || true)"
cat > "$tmp/manifest.json" <<EOF
{
  "created_at": "$stamp",
  "app_version": "${APP_VERSION:-unknown}",
  "image_id": "$image_id",
  "database": "database.dump",
  "uploads": "uploads.tar.gz",
  "alembic": "alembic-current.txt"
}
EOF
output="runtime-data/backups/jobhunt-${stamp}.tar.gz.enc"
tar -C "$tmp" -czf - database.dump uploads.tar.gz alembic-current.txt manifest.json \
  | openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_ENCRYPTION_PASSPHRASE \
  -out "$output"
chmod 600 "$output"
printf '%s\n' "$output"
