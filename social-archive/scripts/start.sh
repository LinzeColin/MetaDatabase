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
.venv/bin/python scripts/ensure_api_token.py --token-file runtime/secrets/social_archive_api_token
# Compose 的 file-backed secret 按 inode 绑定。令牌是幂等的（已存在就不动），
# 但首次生成会换掉 inode，所以仍然强制重建两个非 root 的 Core 服务，
# 让它们挂到当前这个 Secret 上。
docker compose up -d --force-recreate core-api core-worker
for _ in $(seq 1 30); do
  if curl -fsS "${CORE_LOOPBACK_URL}/health" >/dev/null 2>&1; then
    printf 'Social Archive 已启动：%s\n打开档案馆页面登录后，浏览器插件会自动接上，无需输入任何内容。\n' "$CORE_LOOPBACK_URL"
    exit 0
  fi
  sleep 1
done
printf '启动未通过健康检查。请运行：bash scripts/doctor.sh\n' >&2
exit 1
