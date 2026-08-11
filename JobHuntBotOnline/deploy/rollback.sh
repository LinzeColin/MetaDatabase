#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
target="${1:-}"
if [[ -z "$target" && -f runtime-data/rollback-image.txt ]]; then
  target="$(cat runtime-data/rollback-image.txt)"
fi
[[ -n "$target" ]] || { echo "rollback image is missing" >&2; exit 2; }
current_tag="${APP_IMAGE:-jobhuntbot-online:0.3.0}"
docker image inspect "$target" >/dev/null
docker tag "$target" "$current_tag"
docker compose up -d --no-build --force-recreate web scheduler worker
for _ in $(seq 1 60); do
  if curl -fsS "${BASE_URL%/}/readyz" >/dev/null 2>&1; then
    echo "application rollback completed; database was not reverted"
    exit 0
  fi
  sleep 3
done
echo "rollback image started but HTTPS readiness failed" >&2
exit 1
