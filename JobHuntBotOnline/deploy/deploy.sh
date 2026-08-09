#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed on this server." >&2
  exit 2
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose is not available." >&2
  exit 2
fi
if [[ ! -f .env ]]; then
  echo ".env is missing. Run deploy/generate_env.py with the chosen domain and Owner email." >&2
  exit 2
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

data_path="${DATA_PATH:-./runtime-data}"
data_gid="${HOST_DATA_GID:-$(id -g)}"
mkdir -p "$data_path"/{uploads,backups,canonical}
if [[ $(id -u) -eq 0 ]]; then
  chown -R "10001:${data_gid}" "$data_path"
  find "$data_path" -type d -exec chmod 2770 {} +
  find "$data_path" -type f -exec chmod 0660 {} +
elif command -v sudo >/dev/null 2>&1; then
  sudo chown -R "10001:${data_gid}" "$data_path"
  sudo find "$data_path" -type d -exec chmod 2770 {} +
  sudo find "$data_path" -type f -exec chmod 0660 {} +
else
  echo "Cannot prepare private runtime-data ownership. Run this script as a user with sudo." >&2
  exit 2
fi

# Preserve both data and the exact previously runnable image before replacing anything.
previous_image_available=false
current_image_id="$(docker compose images -q app 2>/dev/null | head -n 1 || true)"
if [[ -n "$current_image_id" ]] && docker image inspect "$current_image_id" >/dev/null 2>&1; then
  docker tag "$current_image_id" jobhuntos-online:previous
  previous_image_available=true
elif docker image inspect jobhuntos-online:0.2.0 >/dev/null 2>&1; then
  docker tag jobhuntos-online:0.2.0 jobhuntos-online:previous
  previous_image_available=true
elif docker image inspect jobhuntos-online:0.1.0 >/dev/null 2>&1; then
  docker tag jobhuntos-online:0.1.0 jobhuntos-online:previous
  previous_image_available=true
fi
if docker compose ps --status running --services 2>/dev/null | grep -qx app; then
  docker compose exec -T app python -m app.cli backup >/dev/null
fi

docker compose build --pull app
docker compose up -d --remove-orphans

# Upgrade any earlier local data in place before accepting the new runtime.
docker compose exec -T app python -m app.cli reencrypt-sensitive
docker compose exec -T app python -m app.cli verify-sensitive-storage

if docker compose exec -T app python -m app.cli doctor; then
  for _ in $(seq 1 30); do
    if docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=3).read()" >/dev/null 2>&1; then
      # Initialize the truthful sync state immediately; optional integration failures remain visible in the UI.
      ops/sync_private_database.sh || true
      ops/sync_r2.sh || true
      echo "application_ready: true"
      echo "url: https://${DOMAIN}"
      exit 0
    fi
    sleep 2
  done
fi

echo "The new application image did not become ready." >&2
docker compose ps >&2
docker compose logs --tail=120 app >&2
if [[ "$previous_image_available" == true ]]; then
  echo "Restoring the previously runnable image." >&2
  docker tag jobhuntos-online:previous jobhuntos-online:0.2.0
  docker compose up -d --force-recreate app
  docker compose exec -T app python -m app.cli doctor
  echo "rollback_result: previous_image_restored" >&2
else
  echo "rollback_result: no_previous_image_initial_deploy" >&2
fi
exit 1
