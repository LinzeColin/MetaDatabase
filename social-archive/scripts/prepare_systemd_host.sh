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
# 密钥组与数据组是**两个**组：数据组管写产出，密钥组管读 /run/secrets/。
SECRETS_GROUP="socialarchive-secrets"
# Core runs unprivileged as this uid. It owns the shared bind data root; the
# dedicated host service account is granted group access only to that data root.
# Long-lived source secrets stay root-owned and are handed to a unit through
# systemd LoadCredential=, never through a shared Unix group.
CORE_CONTAINER_UID="10001"
HOST_DATA_ROOT="/var/lib/social-archive"

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

# Source files remain in runtime/secrets. PID 1 alone opens them for the
# named systemd units and provides short-lived per-unit credential copies.
# The script never changes their ownership or mode.
HOST_SECRET_NAMES=(
  r2_access_key_id
  r2_secret_access_key
  oci_access_key_id
  oci_secret_access_key
  github_token
  private_database_token
  social_archive_api_token
  google_oauth_client_secret
  github_oauth_client_secret
  credential_age_identity
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

env_value() {
  file_env_value "$ROOT/.env" "$1"
}

file_env_value() {
  local file="$1"
  local key="$2"
  sed -n -E "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*([^[:space:]#]+)[[:space:]]*$/\1/p" "$file" | tail -n 1
}

is_unit_credential_file_key() {
  case "$1" in
    SOCIAL_ARCHIVE_API_TOKEN_FILE|SOCIAL_ARCHIVE_CLI_WORKER_TOKEN_FILE|SOCIAL_ARCHIVE_R2_ACCESS_KEY_ID_FILE|SOCIAL_ARCHIVE_R2_SECRET_ACCESS_KEY_FILE|SOCIAL_ARCHIVE_OCI_ACCESS_KEY_ID_FILE|SOCIAL_ARCHIVE_OCI_SECRET_ACCESS_KEY_FILE|SOCIAL_ARCHIVE_GITHUB_TOKEN_FILE|SOCIAL_ARCHIVE_PRIVATE_DB_TOKEN_FILE|SOCIAL_ARCHIVE_NOTION_TOKEN_FILE|SOCIAL_ARCHIVE_OBSIDIAN_REST_TOKEN_FILE|SOCIAL_ARCHIVE_KARAKEEP_TOKEN_FILE|SOCIAL_ARCHIVE_LINKWARDEN_TOKEN_FILE)
      return 0
      ;;
  esac
  return 1
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
  [[ "$(env_value SOCIAL_ARCHIVE_DATA_HOST_PATH)" == "$HOST_DATA_ROOT" ]] || fail "生产 SOCIAL_ARCHIVE_DATA_HOST_PATH 必须精确为 ${HOST_DATA_ROOT}，禁止 Core 与 systemd 使用不同数据面。"
  [[ "$(env_value SOCIAL_ARCHIVE_DATA_ROOT)" == "$HOST_DATA_ROOT" ]] || fail "生产 SOCIAL_ARCHIVE_DATA_ROOT 必须精确为 ${HOST_DATA_ROOT}。"
  [[ "$(env_value SOCIAL_ARCHIVE_IMPORT_HOST_PATH)" == "$HOST_DATA_ROOT/import" ]] || fail "生产 SOCIAL_ARCHIVE_IMPORT_HOST_PATH 必须精确为 $HOST_DATA_ROOT/import，禁止 Core 与宿主机分裂导入面。"
  [[ "$(env_value SOCIAL_ARCHIVE_VENDOR_OUTPUT_HOST_PATH)" == "$HOST_DATA_ROOT/vendor-output" ]] || fail "生产 SOCIAL_ARCHIVE_VENDOR_OUTPUT_HOST_PATH 必须精确为 $HOST_DATA_ROOT/vendor-output，禁止 Core 与 CLI Sidecar 分裂输出面。"
  [[ "$(env_value SOCIAL_ARCHIVE_HOST_DATA_GID)" =~ ^[0-9]+$ ]] || fail 'SOCIAL_ARCHIVE_HOST_DATA_GID 必须是宿主机 socialarchive 组的数字 gid。'
  [[ "$(env_value SOCIAL_ARCHIVE_HOST_SECRETS_GID)" =~ ^[0-9]+$ ]] || fail 'SOCIAL_ARCHIVE_HOST_SECRETS_GID 必须是宿主机 socialarchive-secrets 组的数字 gid。缺了它，CLI Sidecar 读不到 /run/secrets/（C-T00-01）。'
  [[ "$(env_value SOCIAL_ARCHIVE_HOST_SECRETS_GID)" != "$(env_value SOCIAL_ARCHIVE_HOST_DATA_GID)" ]] || fail '数据组与密钥组不能是同一个 gid：写产出要 socialarchive，读密钥要 socialarchive-secrets。配成一样必然有一边坏掉。'
  private_database_client="$(env_value SOCIAL_ARCHIVE_PRIVATE_DB_CLIENT)"
  [[ -n "$private_database_client" ]] || fail '缺少 SOCIAL_ARCHIVE_PRIVATE_DB_CLIENT；禁止回退到本地 Private-Database 工作树。'
  [[ "$(basename "$private_database_client")" == "private_db_client.py" && -f "$private_database_client" && ! -L "$private_database_client" ]] || fail 'SOCIAL_ARCHIVE_PRIVATE_DB_CLIENT 必须指向已安装、非符号链接的官方 private_db_client.py；禁止 clone 或挂载 Private-Database。'
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
    if is_unit_credential_file_key "$key"; then
      continue
    fi
    normalized="$(printf '%s' "$key" | tr '[:lower:]' '[:upper:]')"
    case "$normalized" in
      *TOKEN|*SECRET|*PASSWORD|*COOKIE|*SESSION)
        fail ".env 不得包含凭据值：${key}；请使用 runtime/secrets 文件。"
        ;;
    esac
    printf '%s\n' "$line" >> "$output"
  done < "$ROOT/.env"

  cat >> "$output" <<EOF

# 由 prepare_systemd_host.sh 生成。各 service 的 Secret 文件路径由
# LoadCredential= 在启动时注入，禁止在此长期环境文件中保存 source 路径或凭据值。
SOCIAL_ARCHIVE_DATA_ROOT=$HOST_DATA_ROOT
SOCIAL_ARCHIVE_RUNTIME_DB=$HOST_DATA_ROOT/runtime/social-archive.sqlite3
SOCIAL_ARCHIVE_STAGING_ROOT=$HOST_DATA_ROOT/staging
SOCIAL_ARCHIVE_WATCH_ROOT=$HOST_DATA_ROOT/import
SOCIAL_ARCHIVE_EXPORT_ROOT=$HOST_DATA_ROOT/exports
SOCIAL_ARCHIVE_CLI_OUTPUT_ROOT=$HOST_DATA_ROOT/vendor-output/cli
EOF
}

validate_host_env_replacement() {
  [[ -f "$HOST_ENV_FILE" ]] || return 0
  while IFS= read -r key; do
    [[ -n "$key" ]] || continue
    is_unit_credential_file_key "$key" && continue
    existing_value="$(file_env_value "$HOST_ENV_FILE" "$key")"
    source_value="$(env_value "$key")"
    if [[ -n "$existing_value" && -z "$source_value" ]]; then
      fail "现有 $HOST_ENV_FILE 的 $key 有值，但 .env 未声明；拒绝覆盖并清空既有非 Secret 配置。"
    fi
  done < <(sed -n -E 's/^[[:space:]]*(SOCIAL_ARCHIVE_[A-Z0-9_]+)[[:space:]]*=.*/\1/p' "$HOST_ENV_FILE" | sort -u)
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
command -v install >/dev/null || fail '缺少 install。'
command -v systemctl >/dev/null || fail '缺少 systemctl（仅支持 systemd Linux 宿主机）。'
command -v stat >/dev/null || fail '缺少 stat。'

validate_host_env_replacement

if ! id "$SYSTEM_USER" >/dev/null 2>&1; then
  useradd --system --user-group --home-dir /var/lib/social-archive --create-home --shell /usr/sbin/nologin "$SYSTEM_USER"
fi

host_data_gid="$(id -g "$SYSTEM_USER")"
[[ "$(env_value SOCIAL_ARCHIVE_HOST_DATA_GID)" == "$host_data_gid" ]] || fail "SOCIAL_ARCHIVE_HOST_DATA_GID 必须精确等于 $SYSTEM_USER 的 gid ($host_data_gid)，否则 CLI Sidecar 无法写入共享数据根。"

# **写产出和读密钥是两个组，不能共用一个变量。**（C-T00-01）
#   /var/lib/social-archive/vendor-output  10001:980   2770 → 要 socialarchive
#   /run/secrets/*                         10001:10001 0640 → 要 socialarchive-secrets
# 只给前者，容器 /health 照样 200 而业务路由一律 401，界面永远「同步中」。
if ! getent group "$SECRETS_GROUP" >/dev/null 2>&1; then
  groupadd --system "$SECRETS_GROUP"
fi
host_secrets_gid="$(getent group "$SECRETS_GROUP" | cut -d: -f3)"
[[ "$(env_value SOCIAL_ARCHIVE_HOST_SECRETS_GID)" == "$host_secrets_gid" ]] || fail "SOCIAL_ARCHIVE_HOST_SECRETS_GID 必须精确等于 $SECRETS_GROUP 的 gid ($host_secrets_gid)，否则 CLI Sidecar 读不到 /run/secrets/ 下的密钥（这正是 C-T00-01）。"

# These paths are deliberately shallow: the command establishes only new data
# directories and never recursively changes ownership of existing user objects.
# Core's entrypoint uses umask 0007, so newly created SQLite/CAS files inherit
# this group and remain writable by the constrained host maintenance account.
for shared_path in \
  "$HOST_DATA_ROOT" \
  "$HOST_DATA_ROOT/runtime" \
  "$HOST_DATA_ROOT/staging" \
  "$HOST_DATA_ROOT/import" \
  "$HOST_DATA_ROOT/exports" \
  "$HOST_DATA_ROOT/vendor-output" \
  "$HOST_DATA_ROOT/vendor-output/cli" \
  "$HOST_DATA_ROOT/status"; do
  install -d -m 2770 -o "$CORE_CONTAINER_UID" -g "$SYSTEM_USER" "$shared_path"
done

# A pre-existing journal is never silently re-owned. Its metadata must already
# allow both the Core owner and the host service group to update SQLite safely.
runtime_db="$HOST_DATA_ROOT/runtime/social-archive.sqlite3"
if [[ -e "$runtime_db" ]]; then
  runtime_uid="$(stat -c '%u' "$runtime_db")"
  runtime_gid="$(stat -c '%g' "$runtime_db")"
  runtime_mode="$(stat -c '%a' "$runtime_db")"
  host_gid="$(id -g "$SYSTEM_USER")"
  if [[ "$runtime_uid" != "$CORE_CONTAINER_UID" || "$runtime_gid" != "$host_gid" || $((8#$runtime_mode & 0020)) -eq 0 ]]; then
    fail "现有 Runtime SQLite 不满足 Core uid 与 $SYSTEM_USER group 的共同写入条件；未修改该文件，请先完成受控迁移。"
  fi
fi

# Repository-scoped GitHub source credentials must remain root-only.  systemd
# obtains read-only per-unit copies through LoadCredential= at process start.
for root_only_secret in github_token private_database_token; do
  source_secret="$ROOT/runtime/secrets/$root_only_secret"
  if [[ -s "$source_secret" ]]; then
    secret_mode="$(stat -c '%a' "$source_secret")"
    secret_uid="$(stat -c '%u' "$source_secret")"
    secret_gid="$(stat -c '%g' "$source_secret")"
    [[ "$secret_mode" == "600" && "$secret_uid" == "0" && "$secret_gid" == "0" ]] || fail "$root_only_secret 已设置时必须保持 root:root 0600；禁止通过组权限共享。"
  fi
done

install -d -m 0750 -o root -g "$SYSTEM_USER" "$HOST_ENV_DIR"
install -d -m 0700 -o root -g root "$BACKUP_ROOT"
backup_dir="$(mktemp -d "$BACKUP_ROOT/systemd-prepare.XXXXXX")"
[[ -e "$HOST_ENV_FILE" ]] && cp -p "$HOST_ENV_FILE" "$backup_dir/"
for unit in "${UNITS[@]}"; do
  unit_path="$SYSTEMD_DIR/$unit"
  [[ -e "$unit_path" ]] && cp -p "$unit_path" "$backup_dir/"
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

# **把「要启用什么」逐条列出来，不要只说「由 Owner 显式启用」。**
#
# 生产实测（2026-08-04）：只有 social-archive.service 与 status.timer 被启用过，
# 而 backup / replication / private-database-sync 三个 timer 一直是 disabled，
# journalctl 90 天内 "No entries" —— **从来没跑过**。
# 后果：549 个制品里 530 个一个异地副本都没有，也没有任何定时备份。
# 对一个以「归档」为卖点的产品，这是最要命的那种沉默失败。
#
# 这里**只列名字，不写启用命令**：validate_systemd.py 明令本脚本里不许出现
# 那两个动词，而那条规矩是对的——装好与启用必须是两个人为分开的动作。
# 具体命令交给 scripts/check_durability_units.sh，它是只读检查器，不是准备器。
printf '\n必须由 Owner 显式启用的 unit（缺一个就有数据只存在一份的风险）：\n'
printf '  social-archive.service\n'
printf '  social-archive-backup.timer                  —— 定时备份\n'
printf '  social-archive-replication.timer             —— 三地副本\n'
printf '  social-archive-private-database-sync.timer   —— 私有库同步\n'
printf '  social-archive-status.timer\n'
printf '  social-archive-cloudflared.service\n'
printf '\n启用命令与逐项核对：bash scripts/check_durability_units.sh\n'
