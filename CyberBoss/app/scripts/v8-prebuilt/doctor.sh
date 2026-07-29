#!/usr/bin/env bash
set -euo pipefail
fail(){ printf '%s\n' "未通过：$1" >&2; exit 1; }
[[ "$(id -u)" != 0 ]] || true
node --version | grep -Eq '^v(2[2-9]|[3-9][0-9])\.' || fail '需要 Node.js 22 或更高版本'
[[ -r "${CYBERBOSS_DB_PATH:-/var/lib/cyberboss/runtime.sqlite3}" ]] || fail '运行数据库尚未初始化'
[[ "${CYBERBOSS_LISTEN_HOST:-127.0.0.1}" == 127.0.0.1 ]] || fail '应用必须仅监听本机回环地址'

cred_dir="${CREDENTIALS_DIRECTORY:-/run/credentials/cyberboss.service}"
[[ -r "$cred_dir/deepseek-api-key" ]] || [[ -n "${DEEPSEEK_API_KEY:-}" ]] || fail '缺少 DeepSeek API 凭据'
if [[ -r "$cred_dir/deepseek-api-key" ]]; then
  size=$(wc -c < "$cred_dir/deepseek-api-key")
  [[ "$size" -ge 8 && "$size" -le 4096 ]] || fail 'DeepSeek API 凭据文件无效'
fi
printf '%s\n' 'CyberBoss 运行前检查通过'
