#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
if [[ -n "${LEGACY_COMPOSE_FILE:-}" ]]; then
  [[ -f "$LEGACY_COMPOSE_FILE" ]] || { echo "LEGACY_COMPOSE_FILE does not exist" >&2; exit 2; }
  legacy_project_dir="$(cd "$(dirname "$LEGACY_COMPOSE_FILE")" && pwd)"
  legacy_service="${LEGACY_SERVICE:-app}"
  docker compose --profile canary stop web web-canary scheduler worker >/dev/null 2>&1 || true
  docker compose --project-directory "$legacy_project_dir" -f "$LEGACY_COMPOSE_FILE" up -d "$legacy_service"
  for _ in $(seq 1 60); do
    if curl -fsS "${BASE_URL%/}/readyz" >/dev/null 2>&1; then
      echo "legacy application rollback completed; PostgreSQL was not reverted"
      exit 0
    fi
    sleep 3
  done
  echo "legacy application rollback started but HTTPS readiness failed" >&2
  exit 1
fi
target="${1:-}"
if [[ -z "$target" && -f runtime-data/rollback-image.txt ]]; then
  target="$(cat runtime-data/rollback-image.txt)"
fi
[[ -n "$target" ]] || { echo "rollback image is missing" >&2; exit 2; }
current_tag="${APP_IMAGE:-jobhuntbot-online:0.4.0}"
docker image inspect "$target" >/dev/null
docker tag "$target" "$current_tag"
docker compose --profile canary up -d --no-build --force-recreate web web-canary scheduler worker
for _ in $(seq 1 60); do
  if curl -fsS "${BASE_URL%/}/readyz" >/dev/null 2>&1; then
    echo "application rollback completed; database was not reverted"
    exit 0
  fi
  sleep 3
done
echo "rollback image started but HTTPS readiness failed" >&2
exit 1
