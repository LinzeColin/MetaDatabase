#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
# shellcheck disable=SC1091
source .env
set +a
status_file="${DATA_PATH:-./runtime-data}/canonical/sync_status.json"

if [[ "${R2_SYNC_ENABLED:-false}" != "true" ]]; then
  python3 ops/update_sync_status.py --file "$status_file" --channel objects --state not_configured --message "R2 同步因零付费守卫未通过而保持禁用"
  exit 0
fi
if [[ -z "${RCLONE_R2_REMOTE:-}" ]]; then
  python3 ops/update_sync_status.py --file "$status_file" --channel objects --state not_configured --message "R2 加密对象备份未配置"
  exit 0
fi
if ! command -v rclone >/dev/null 2>&1; then
  python3 ops/update_sync_status.py --file "$status_file" --channel objects --state failed --message "服务器缺少 rclone"
  exit 1
fi

rclone copy "${DATA_PATH:-./runtime-data}/uploads" "${RCLONE_R2_REMOTE%/}/uploads" --fast-list --create-empty-src-dirs
rclone copy "${DATA_PATH:-./runtime-data}/backups" "${RCLONE_R2_REMOTE%/}/backups" --fast-list --create-empty-src-dirs
rclone copy "${DATA_PATH:-./runtime-data}/canonical" "${RCLONE_R2_REMOTE%/}/canonical" --fast-list --exclude sync_status.json
python3 ops/update_sync_status.py --file "$status_file" --channel objects --state synced --message "加密原文件与恢复包已同步到 R2"
