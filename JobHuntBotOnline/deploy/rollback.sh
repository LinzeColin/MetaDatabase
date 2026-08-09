#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo ".env is missing." >&2
  exit 2
fi
if ! docker image inspect jobhuntos-online:previous >/dev/null 2>&1; then
  echo "No previous application image is available." >&2
  exit 2
fi

# Preserve current data before changing code. Data is not silently rolled back.
docker compose exec -T app python -m app.cli backup >/dev/null || true
docker tag jobhuntos-online:previous jobhuntos-online:0.2.0
docker compose up -d --force-recreate app
docker compose exec -T app python -m app.cli doctor
for _ in $(seq 1 30); do
  if docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=3).read()" >/dev/null 2>&1; then
    echo "rollback_result: previous_image_ready"
    exit 0
  fi
  sleep 2
done

echo "Previous image did not become ready; inspect deploy/diagnose.sh output." >&2
exit 1
