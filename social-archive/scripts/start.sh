#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -x .venv/bin/python ]] || { printf '请先运行 bash scripts/install.sh\n' >&2; exit 2; }
core_loopback_port() {
  local value="${SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT:-}"
  if [[ -z "$value" && -f .env ]]; then
    value="$(awk -F= '$1 == "SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT" {value=$2} END {print value}' .env | tr -d '[:space:]')"
  fi
  value="${value:-18765}"
  if ! [[ "$value" =~ ^[0-9]+$ ]] || (( value < 1 || value > 65535 )); then
    printf '启动停止：SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT 必须介于 1 和 65535。\n' >&2
    exit 2
  fi
  printf '%s\n' "$value"
}
CORE_LOOPBACK_PORT="$(core_loopback_port)"
CORE_LOOPBACK_URL="http://127.0.0.1:${CORE_LOOPBACK_PORT}"
docker network inspect social-archive-readers >/dev/null 2>&1 || docker network create social-archive-readers >/dev/null
mkdir -p runtime/secrets
PAIRING_CODE="$(.venv/bin/python scripts/generate_pairing_code.py --code-file runtime/secrets/social_archive_pairing_code --token-file runtime/secrets/social_archive_api_token --ttl-seconds 600)"
# Compose file-backed secrets are bind-mounted by inode.  The pairing generator
# atomically replaces its file, so a normal `up -d` can retain an old mount and
# make the newly printed code unusable.  Recreate both non-root Core services
# after each code refresh to attach the current Secret inode.
docker compose up -d --force-recreate core-api core-worker
for _ in $(seq 1 30); do
  if curl -fsS "${CORE_LOOPBACK_URL}/health" >/dev/null 2>&1; then
    printf 'Social Archive 已启动：%s\n浏览器插件一次性配对码：%s（10 分钟有效，最多 5 次尝试）\n' "$CORE_LOOPBACK_URL" "$PAIRING_CODE"
    exit 0
  fi
  sleep 1
done
printf '启动未通过健康检查。请运行：bash scripts/doctor.sh\n' >&2
exit 1
