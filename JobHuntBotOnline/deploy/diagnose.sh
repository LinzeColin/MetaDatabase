#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== containers =="
docker compose ps
echo "== application diagnostics =="
docker compose exec -T app python -m app.cli doctor || true
echo "== application logs =="
docker compose logs --tail=160 app
echo "== proxy logs =="
proxy_container="${TRAEFIK_PROXY_CONTAINER:-coolify-proxy}"
docker inspect "$proxy_container" --format '{{.State.Status}} {{.Config.Image}}' || true
