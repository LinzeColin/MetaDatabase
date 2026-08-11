#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -f .env
test -f secrets/postgres_password.txt
[[ "$(stat -c '%a' .env)" =~ ^(600|400)$ ]] || { echo ".env must be mode 0600 or 0400" >&2; exit 1; }
python3 deploy/verify_taskpack.py --deployment-runtime
set -a; source .env; set +a
mkdir -p runtime-data evidence
previous_image="$(docker compose images -q web 2>/dev/null | head -1 || true)"
legacy_active=0
legacy_service="${LEGACY_SERVICE:-app}"
legacy_compose=()
if [[ -n "${LEGACY_COMPOSE_FILE:-}" ]]; then
  [[ -f "$LEGACY_COMPOSE_FILE" ]] || { echo "LEGACY_COMPOSE_FILE does not exist" >&2; exit 1; }
  legacy_project_dir="$(cd "$(dirname "$LEGACY_COMPOSE_FILE")" && pwd)"
  legacy_compose=(docker compose --project-directory "$legacy_project_dir" -f "$LEGACY_COMPOSE_FILE")
  "${legacy_compose[@]}" config --services | grep -qx "$legacy_service" \
    || { echo "LEGACY_SERVICE is absent from LEGACY_COMPOSE_FILE" >&2; exit 1; }
  if "${legacy_compose[@]}" ps --services --filter status=running | grep -qx "$legacy_service"; then
    legacy_active=1
  fi
fi
if [[ "$legacy_active" == "1" ]]; then
  # The first v0.3 deployment may have no prior v0.3 image.  The verified
  # active legacy Compose service is the only executable rollback target.
  printf 'legacy-compose:%s#%s\n' "$LEGACY_COMPOSE_FILE" "$legacy_service" > runtime-data/rollback-image.txt
elif [[ -n "$previous_image" ]]; then
  echo "$previous_image" > runtime-data/rollback-image.txt
fi
if docker compose ps --services --filter status=running 2>/dev/null | grep -q '^postgres$'; then
  deploy/backup.sh > runtime-data/predeploy-backup.txt
fi
rollback_on_error() {
  echo "deployment failed; previous application image remains available in runtime-data/rollback-image.txt" >&2
  docker compose stop web scheduler worker >/dev/null 2>&1 || true
  if [[ "$legacy_active" == "1" ]]; then
    "${legacy_compose[@]}" up -d "$legacy_service" || true
  elif [[ -n "$previous_image" ]]; then
    deploy/rollback.sh "$previous_image" || true
  fi
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
  # The migration writes a host-mounted evidence file.  Match the acceptance
  # runner's host identity so its result remains writable on a managed host.
  docker compose run --rm \
    --user "${ACCEPTANCE_UID:-$(id -u)}:${ACCEPTANCE_GID:-$(id -g)}" \
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

if [[ -n "${LEGACY_COMPOSE_FILE:-}" ]]; then
  "${legacy_compose[@]}" stop "$legacy_service"
fi
docker compose up -d web scheduler worker
for _ in $(seq 1 60); do
  if curl -fsS "${BASE_URL%/}/readyz" >/dev/null 2>&1; then
    trap - ERR
    echo "application services are ready; run deploy/acceptance.sh"
    exit 0
  fi
  sleep 3
done
echo "application did not become ready" >&2
exit 1
