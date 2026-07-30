#!/usr/bin/env bash
# Prepare the exact OVH host contract without starting a production service.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
MODE=""
TARGET_ROOT="/opt/social-archive"
HOST_ENV_DIR="/etc/social-archive"
HOST_ENV_FILE="$HOST_ENV_DIR/social-archive.env"
SYSTEMD_DIR="/etc/systemd/system"
BACKUP_ROOT="/var/backups/social-archive"
SYSTEM_USER="socialarchive"
# Docker Compose file-backed secrets preserve the host file's numeric owner.
# Core runs as uid/gid 10001, so host-side secret ownership must deliberately
# bridge that unprivileged container identity and the systemd service user.
CORE_SECRET_GID="10001"
CORE_SECRET_GROUP="socialarchive-secrets"

UNITS=(
  social-archive.service
  social-archive-backup.service
  social-archive-backup.timer
  social-archive-cloudflared.service
  social-archive-private-database-sync.service
  social-archive-private-database-sync.timer
  social-archive-replication.service
  social-archive-replication.timer
  social-archive-status.service
  social-archive-status.timer
  social-archive-status-web.service
)

# These are Docker-secret paths in .env, but host systemd jobs need the same
# files through a non-container path. No credential content is copied.
HOST_SECRET_NAMES=(
  r2_access_key_id
  r2_secret_access_key
  oci_access_key_id
  oci_secret_access_key
  github_token
  social_archive_api_token
  social_archive_pairing_code
  cli_worker_token
  notion_token
  obsidian_rest_token
  karakeep_api_token
  linkwarden_api_token
)

fail() {
  printf 'systemd 宿主机准备停止：%s\n' "$1" >&2
  exit 2
}

usage() {
  printf '%s\n' '用法：bash scripts/prepare_systemd_host.sh --dry-run|--apply'
}

for arg in "$@"; do
  case "$arg" in
    --dry-run|--apply)
      [[ -z "$MODE" ]] || fail '只能指定一个模式。'
      MODE="$arg"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      fail "未知参数：$arg"
      ;;
  esac
done
[[ -n "$MODE" ]] || fail '必须显式指定 --dry-run 或 --apply。'

validate_source_contract() {
  [[ -f "$ROOT/.env" ]] || fail '缺少 .env；先完成 install.sh 和配置向导。'
  [[ -x "$ROOT/.venv/bin/python" ]] || fail '缺少 .venv/bin/python；先完成 install.sh。'
  [[ -f "$ROOT/runtime/secrets/social_archive_api_token" ]] || fail '缺少 runtime/secrets/social_archive_api_token。'
  for unit in "${UNITS[@]}"; do
    [[ -f "$ROOT/deploy/systemd/$unit" ]] || fail "缺少 systemd unit：$unit"
  done
  for secret_name in "${HOST_SECRET_NAMES[@]}"; do
    [[ -f "$ROOT/runtime/secrets/$secret_name" ]] || fail "缺少宿主机 Secret 文件：$secret_name"
  done
}

render_host_env() {
  local output="$1"
  local line key normalized
  : > "$output"
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ -z "${line//[[:space:]]/}" || "$line" =~ ^[[:space:]]*# || "$line" != *=* ]]; then
      printf '%s\n' "$line" >> "$output"
      continue
    fi
    key="${line%%=*}"
    key="${key//[[:space:]]/}"
    case "$key" in
      SOCIAL_ARCHIVE_API_TOKEN_FILE|SOCIAL_ARCHIVE_PAIRING_CODE_FILE|SOCIAL_ARCHIVE_CLI_WORKER_TOKEN_FILE|SOCIAL_ARCHIVE_R2_ACCESS_KEY_ID_FILE|SOCIAL_ARCHIVE_R2_SECRET_ACCESS_KEY_FILE|SOCIAL_ARCHIVE_OCI_ACCESS_KEY_ID_FILE|SOCIAL_ARCHIVE_OCI_SECRET_ACCESS_KEY_FILE|SOCIAL_ARCHIVE_GITHUB_TOKEN_FILE|SOCIAL_ARCHIVE_NOTION_TOKEN_FILE|SOCIAL_ARCHIVE_OBSIDIAN_REST_TOKEN_FILE|SOCIAL_ARCHIVE_KARAKEEP_TOKEN_FILE|SOCIAL_ARCHIVE_LINKWARDEN_TOKEN_FILE)
        continue
        ;;
    esac
    normalized="$(printf '%s' "$key" | tr '[:lower:]' '[:upper:]')"
    case "$normalized" in
      *TOKEN|*SECRET|*PASSWORD|*COOKIE|*SESSION)
        fail ".env 不得包含凭据值：$key；请使用 runtime/secrets 文件。"
        ;;
    esac
    printf '%s\n' "$line" >> "$output"
  done < "$ROOT/.env"

  cat >> "$output" <<EOF

# 由 prepare_systemd_host.sh 生成；仅保存受限 Secret 文件路径，不含凭据值。
SOCIAL_ARCHIVE_API_TOKEN_FILE=$ROOT/runtime/secrets/social_archive_api_token
SOCIAL_ARCHIVE_PAIRING_CODE_FILE=$ROOT/runtime/secrets/social_archive_pairing_code
SOCIAL_ARCHIVE_CLI_WORKER_TOKEN_FILE=$ROOT/runtime/secrets/cli_worker_token
SOCIAL_ARCHIVE_R2_ACCESS_KEY_ID_FILE=$ROOT/runtime/secrets/r2_access_key_id
SOCIAL_ARCHIVE_R2_SECRET_ACCESS_KEY_FILE=$ROOT/runtime/secrets/r2_secret_access_key
SOCIAL_ARCHIVE_OCI_ACCESS_KEY_ID_FILE=$ROOT/runtime/secrets/oci_access_key_id
SOCIAL_ARCHIVE_OCI_SECRET_ACCESS_KEY_FILE=$ROOT/runtime/secrets/oci_secret_access_key
SOCIAL_ARCHIVE_GITHUB_TOKEN_FILE=$ROOT/runtime/secrets/github_token
SOCIAL_ARCHIVE_NOTION_TOKEN_FILE=$ROOT/runtime/secrets/notion_token
SOCIAL_ARCHIVE_OBSIDIAN_REST_TOKEN_FILE=$ROOT/runtime/secrets/obsidian_rest_token
SOCIAL_ARCHIVE_KARAKEEP_TOKEN_FILE=$ROOT/runtime/secrets/karakeep_api_token
SOCIAL_ARCHIVE_LINKWARDEN_TOKEN_FILE=$ROOT/runtime/secrets/linkwarden_api_token
EOF
}

validate_source_contract
if [[ "$MODE" == "--dry-run" ]]; then
  render_host_env /dev/null
  printf '预检通过：systemd unit、.env、venv 和受限 Secret 文件齐全。\n'
  printf '未创建账户、目录、备份、/etc 配置或 unit；未执行 daemon-reload、enable、start、Docker、网络或云操作。\n'
  printf '真实应用必须在 %s 中以 root 显式执行 --apply。\n' "$TARGET_ROOT"
  exit 0
fi

[[ "$ROOT" == "$TARGET_ROOT" ]] || fail "--apply 只允许在 $TARGET_ROOT 执行。"
[[ "$(id -u)" == "0" ]] || fail '--apply 需要 root；请先运行 --dry-run。'
command -v useradd >/dev/null || fail '缺少 useradd（仅支持 systemd Linux 宿主机）。'
command -v groupadd >/dev/null || fail '缺少 groupadd（仅支持 systemd Linux 宿主机）。'
command -v usermod >/dev/null || fail '缺少 usermod（仅支持 systemd Linux 宿主机）。'
command -v getent >/dev/null || fail '缺少 getent（仅支持 systemd Linux 宿主机）。'
command -v install >/dev/null || fail '缺少 install。'
command -v systemctl >/dev/null || fail '缺少 systemctl（仅支持 systemd Linux 宿主机）。'

if ! id "$SYSTEM_USER" >/dev/null 2>&1; then
  useradd --system --user-group --home-dir /var/lib/social-archive --create-home --shell /usr/sbin/nologin "$SYSTEM_USER"
fi

# Reuse an existing gid only deliberately; otherwise create the dedicated
# shared group.  The runtime image uses gid 10001 for both Core and the CLI
# sidecar, while host-side oneshot services run as $SYSTEM_USER.
if ! getent group "$CORE_SECRET_GID" >/dev/null 2>&1; then
  getent group "$CORE_SECRET_GROUP" >/dev/null 2>&1 && fail "组名 $CORE_SECRET_GROUP 已被占用，不能安全创建 gid $CORE_SECRET_GID。"
  groupadd --system --gid "$CORE_SECRET_GID" "$CORE_SECRET_GROUP"
fi
CORE_SECRET_GROUP="$(getent group "$CORE_SECRET_GID" | cut -d: -f1)"
[[ -n "$CORE_SECRET_GROUP" ]] || fail "无法解析 gid $CORE_SECRET_GID 对应的组。"
usermod -a -G "$CORE_SECRET_GROUP" "$SYSTEM_USER"

# The directory grants group execute only (no listing); every individual secret
# stays readable only by Core's uid/gid 10001 or the dedicated shared group.
chown root:"$CORE_SECRET_GROUP" "$ROOT/runtime/secrets"
chmod 0710 "$ROOT/runtime/secrets"

install -d -m 0750 -o root -g "$SYSTEM_USER" "$HOST_ENV_DIR"
install -d -m 0700 -o root -g root "$BACKUP_ROOT"
backup_dir="$(mktemp -d "$BACKUP_ROOT/systemd-prepare.XXXXXX")"
[[ -e "$HOST_ENV_FILE" ]] && cp -p "$HOST_ENV_FILE" "$backup_dir/"
for unit in "${UNITS[@]}"; do
  unit_path="$SYSTEMD_DIR/$unit"
  [[ -e "$unit_path" ]] && cp -p "$unit_path" "$backup_dir/"
done

for secret_name in "${HOST_SECRET_NAMES[@]}"; do
  secret_path="$ROOT/runtime/secrets/$secret_name"
  chown "$CORE_SECRET_GID:$CORE_SECRET_GID" "$secret_path"
  chmod 0640 "$secret_path"
done

umask 077
temporary_env="$(mktemp "$HOST_ENV_DIR/.social-archive.env.XXXXXX")"
trap 'rm -f "$temporary_env"' EXIT
render_host_env "$temporary_env"
install -m 0640 -o root -g "$SYSTEM_USER" "$temporary_env" "$HOST_ENV_FILE"
for unit in "${UNITS[@]}"; do
  install -m 0644 -o root -g root "$ROOT/deploy/systemd/$unit" "$SYSTEMD_DIR/$unit"
done
systemctl daemon-reload

printf '宿主机准备完成；可回滚备份：%s\n' "$backup_dir"
printf '未启用或启动任何 unit、Docker、Tunnel 或云资源；由 Owner 完成下一步验收后再显式启用。\n'
