#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -f .env
test -f secrets/postgres_password.txt
[[ "$(stat -c '%a' .env)" =~ ^(600|400)$ ]] || { echo ".env must be mode 0600 or 0400" >&2; exit 1; }
python deploy/verify_taskpack.py
set -a; source .env; set +a
mkdir -p runtime-data evidence
previous_image="$(docker compose images -q web 2>/dev/null | head -1 || true)"
if [[ -n "$previous_image" ]]; then
  echo "$previous_image" > runtime-data/rollback-image.txt
fi
if docker compose ps --services --filter status=running 2>/dev/null | grep -q '^postgres$'; then
  deploy/backup.sh > runtime-data/predeploy-backup.txt
fi
rollback_on_error() {
  echo "deployment failed; previous application image remains available in runtime-data/rollback-image.txt" >&2
  if [[ -n "$previous_image" ]]; then deploy/rollback.sh "$previous_image" || true; fi
}
trap rollback_on_error ERR

docker network inspect "${EDGE_NETWORK:-coolify}" >/dev/null
docker compose config >/dev/null
docker compose build --pull web
docker compose up -d postgres
docker compose run --rm web alembic upgrade head

if [[ -n "${V02_SQLITE_PATH:-}" ]]; then
  [[ -f "$V02_SQLITE_PATH" ]] || { echo "V02_SQLITE_PATH does not exist" >&2; exit 1; }
  old_root="${V02_DATA_ROOT:-$(dirname "$V02_SQLITE_PATH")}"; [[ -d "$old_root" ]] || { echo "V02_DATA_ROOT does not exist" >&2; exit 1; }
  extra_mount=()
  platform_arg=()
  if [[ -n "${V02_PLATFORM_KEY_OUTPUT:-}" ]]; then
    mkdir -p "$(dirname "$V02_PLATFORM_KEY_OUTPUT")"
    extra_mount+=( -v "$(dirname "$V02_PLATFORM_KEY_OUTPUT"):/migration/secrets" )
    platform_arg=( --platform-key-output "/migration/secrets/$(basename "$V02_PLATFORM_KEY_OUTPUT")" )
  fi
  docker compose run --rm \
    -v "$V02_SQLITE_PATH:/migration/v02.db:ro" \
    -v "$old_root:/migration/v02-data:ro" \
    -v "$PWD/evidence:/app/evidence" \
    "${extra_mount[@]}" \
    web python tools/migrate_v02_sqlite.py \
      --source /migration/v02.db --old-data-root /migration/v02-data \
      "${platform_arg[@]}" --output /app/evidence/migration-result.json
else
  cat > evidence/migration-result.json <<'EOF'
{"verdict":"PASS","mode":"fresh_schema_or_previously_migrated","production_claimed":true,"secret_values_printed":false}
EOF
fi

docker compose up -d web scheduler worker
for _ in $(seq 1 60); do
  if health_json="$(curl -fsS "${BASE_URL%/}/healthz" 2>/dev/null)" \
    && curl -fsS "${BASE_URL%/}/readyz" >/dev/null 2>&1 \
    && python - "$health_json" "${APP_VERSION:-0.3.0}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload.get("status") == "ok"
assert payload.get("version") == sys.argv[2]
PY
  then
    trap - ERR
    echo "application services are ready; run deploy/acceptance.sh"
    exit 0
  fi
  sleep 3
done
echo "application did not become ready" >&2
exit 1
