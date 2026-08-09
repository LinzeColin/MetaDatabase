#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
# shellcheck disable=SC1091
source .env
set +a
status_file="${DATA_PATH:-./runtime-data}/canonical/sync_status.json"

set_status() {
  python3 ops/update_sync_status.py \
    --file "$status_file" \
    --channel structured \
    --state "$1" \
    --message "$2"
}

client_path="${PRIVATE_DATABASE_CLIENT_PATH:-}"
area="${PRIVATE_DATABASE_AREA:-Private-MetaDatabase}"
target_path="${PRIVATE_DATABASE_TARGET_PATH:-products/jobhuntos-online/current.json}"

if [[ -z "$client_path" ]]; then
  set_status not_configured "Private-Database 客户端未配置"
  exit 0
fi
if [[ "$client_path" != /* ]]; then
  client_path="$PWD/$client_path"
fi
if [[ ! -f "$client_path" ]]; then
  set_status failed "Private-Database 客户端不可用"
  exit 1
fi
if ! command -v gh >/dev/null 2>&1 || ! gh auth status >/dev/null 2>&1; then
  set_status not_configured "部署节点未提供已授权的 Private-Database GitHub 客户端"
  exit 0
fi
if [[ "$target_path" = /* || "$target_path" == *".."* ]]; then
  set_status failed "Private-Database 目标路径不安全"
  exit 1
fi

if ! docker compose exec -T app python -m app.cli export >/dev/null; then
  set_status failed "应用无法导出结构化事实"
  exit 1
fi
source_file="${DATA_PATH:-./runtime-data}/canonical/current.json"
if [[ ! -r "$source_file" ]]; then
  set_status failed "宿主同步用户无法读取结构化导出"
  exit 1
fi
if ! python3 "$client_path" put "$area" "$target_path" "$source_file"; then
  set_status failed "Private-Database 无法写入结构化导出"
  exit 1
fi
set_status synced "结构化事实已同步到 Private-Database"
