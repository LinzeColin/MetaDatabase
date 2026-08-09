#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo ".env is missing." >&2
  exit 2
fi
set -a
# shellcheck disable=SC1091
source .env
set +a
if [[ $# -ne 1 ]]; then
  echo "Usage: deploy/restore.sh runtime-data/backups/<file>.jhbbackup" >&2
  exit 2
fi
if [[ ! -f "$1" ]]; then
  echo "Backup file not found." >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose is required." >&2
  exit 2
fi
if ! docker image inspect jobhuntos-online:0.2.0 >/dev/null 2>&1; then
  echo "The JobHuntBot Online application image is unavailable." >&2
  exit 2
fi

backup=$(realpath "$1")
data_path=$(realpath -m "${DATA_PATH:-./runtime-data}")
parent=$(dirname "$data_path")
base=$(basename "$data_path")
stamp=$(date -u +%Y%m%dT%H%M%SZ)
staging="$parent/.${base}.restore-staging.${stamp}"
previous="$parent/${base}.before-restore.${stamp}"
failed="$parent/${base}.failed-restore.${stamp}"
input_dir="$parent/.${base}.restore-input.${stamp}"
input_copy="$input_dir/input.jhbbackup"
data_gid="${HOST_DATA_GID:-$(id -g)}"

if [[ ! -d "$data_path" ]]; then
  echo "Current data directory does not exist: $data_path" >&2
  exit 2
fi
if [[ -e "$staging" || -e "$previous" || -e "$failed" || -e "$input_dir" ]]; then
  echo "A restore staging path already exists; inspect before retrying." >&2
  exit 2
fi
mkdir -p "$staging" "$input_dir"
if [[ $(id -u) -eq 0 ]]; then
  chown -R "10001:${data_gid}" "$staging" "$input_dir"
elif command -v sudo >/dev/null 2>&1; then
  sudo chown -R "10001:${data_gid}" "$staging" "$input_dir"
else
  echo "Cannot prepare private restore staging ownership. Run as a user with sudo." >&2
  exit 2
fi
chmod 2770 "$staging" "$input_dir"
cp "$backup" "$input_copy"
if [[ $(id -u) -eq 0 ]]; then
  chown "10001:${data_gid}" "$input_copy"
elif command -v sudo >/dev/null 2>&1; then
  sudo chown "10001:${data_gid}" "$input_copy"
fi
chmod 0640 "$input_copy"

cleanup_staging() {
  if [[ -d "$staging" ]]; then
    rm -rf "$staging" 2>/dev/null || sudo rm -rf "$staging"
  fi
  if [[ -d "$input_dir" ]]; then
    rm -rf "$input_dir" 2>/dev/null || sudo rm -rf "$input_dir"
  fi
}
trap cleanup_staging EXIT

docker compose down

# Restore only into an empty staging directory. The live directory is untouched
# until the restored database, protected fields and upload objects all validate.
docker run --rm \
  --env-file .env \
  -e DATA_DIR=/data \
  -e DATABASE_URL=sqlite:////data/jobhuntos.db \
  -v "$staging:/data" \
  -v "$input_copy:/restore/input.jhbbackup:ro" \
  jobhuntos-online:0.2.0 \
  python -m app.cli restore /restore/input.jhbbackup /data

docker run --rm \
  --env-file .env \
  -e DATA_DIR=/data \
  -e DATABASE_URL=sqlite:////data/jobhuntos.db \
  -v "$staging:/data" \
  jobhuntos-online:0.2.0 \
  python -m app.cli reencrypt-sensitive

docker run --rm \
  --env-file .env \
  -e DATA_DIR=/data \
  -e DATABASE_URL=sqlite:////data/jobhuntos.db \
  -v "$staging:/data" \
  jobhuntos-online:0.2.0 \
  python -m app.cli verify-sensitive-storage

docker run --rm \
  --env-file .env \
  -e DATA_DIR=/data \
  -e DATABASE_URL=sqlite:////data/jobhuntos.db \
  -v "$staging:/data" \
  jobhuntos-online:0.2.0 \
  python -m app.cli doctor

mv "$data_path" "$previous"
mv "$staging" "$data_path"
rm -rf "$input_dir" 2>/dev/null || sudo rm -rf "$input_dir"
trap - EXIT

docker compose up -d
for _ in $(seq 1 30); do
  if docker compose exec -T app python -m app.cli doctor >/dev/null 2>&1 && \
     docker compose exec -T app python -m app.cli verify-sensitive-storage >/dev/null 2>&1; then
    echo "restore_result: ready"
    echo "pre_restore_data: $previous"
    exit 0
  fi
  sleep 2
done

echo "Restored application did not become ready; reverting to the pre-restore data directory." >&2
docker compose down || true
mv "$data_path" "$failed"
mv "$previous" "$data_path"
docker compose up -d
for _ in $(seq 1 30); do
  if docker compose exec -T app python -m app.cli doctor >/dev/null 2>&1; then
    echo "restore_result: reverted_to_previous_data" >&2
    echo "failed_restore_data: $failed" >&2
    exit 1
  fi
  sleep 2
done

echo "Both restored and previous data failed readiness; manual incident handling is required." >&2
exit 1
