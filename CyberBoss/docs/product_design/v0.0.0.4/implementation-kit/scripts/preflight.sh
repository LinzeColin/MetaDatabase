#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK_ONLY=0
OUTPUT_PATH=""

while (($#)); do
  case "$1" in
    --check)
      CHECK_ONLY=1
      shift
      ;;
    --output)
      OUTPUT_PATH="${2:-}"
      shift 2
      ;;
    *)
      echo "PREFLIGHT=FAIL unknown_arg:$1"
      exit 2
      ;;
  esac
done

if ((CHECK_ONLY)) && [[ -n "$OUTPUT_PATH" ]]; then
  echo "PREFLIGHT=FAIL check_is_read_only"
  exit 2
fi
if [[ -n "$OUTPUT_PATH" && "$OUTPUT_PATH" != /* ]]; then
  echo "PREFLIGHT=FAIL output_path_must_be_absolute"
  exit 2
fi

CB_PREFLIGHT_TMP="$(mktemp -d -t cyberboss-preflight.XXXXXX)"
trap 'rm -rf "$CB_PREFLIGHT_TMP"' EXIT

if ((CHECK_ONLY)); then
  cat >"$CB_PREFLIGHT_TMP/check-measurement.json" <<'JSON'
{
  "schema_version": 1,
  "source": "clean_shell_check_fixture",
  "captured_at": "fixture",
  "memory": {
    "total_mb": 4096,
    "available_mb": 3000,
    "swap_total_mb": 1024,
    "swap_free_mb": 1024
  },
  "load": {"one_minute": 0.5, "cpu_count": 2},
  "storage": {
    "root": {
      "free_mb": 25000,
      "used_percent": 40,
      "inode_used_percent": 10
    }
  },
  "queue": {"depth": 0}
}
JSON
  "$SCRIPT_DIR/select-resource-profile.sh" \
    --measurements "$CB_PREFLIGHT_TMP/check-measurement.json" \
    --check >"$CB_PREFLIGHT_TMP/profile-check.txt"
  grep -q '^PROFILE_CHECK=PASS$' "$CB_PREFLIGHT_TMP/profile-check.txt"
  grep -q '^CB_RESOURCE_ACTIVATION_SAFE=true$' "$CB_PREFLIGHT_TMP/profile-check.txt"
  PYTHONPYCACHEPREFIX="$CB_PREFLIGHT_TMP/pycache" python3 -m py_compile \
    "$SCRIPT_DIR/resource_profile.py" \
    "$SCRIPT_DIR/resource-pressure-fixture.py"
  echo "PREFLIGHT_CHECK=PASS live_commands=false persistent_writes=false temp_cleanup=true snapshots=3"
  exit 0
fi

if [[ ! -r /proc/meminfo ]]; then
  echo "PREFLIGHT=FAIL live_collection_requires_linux_procfs"
  exit 2
fi

REMEDIATIONS=()
WARNINGS=()
have() { command -v "$1" >/dev/null 2>&1; }
remediate() { REMEDIATIONS+=("$1"); }
warn() { WARNINGS+=("$1"); }

for command_name in bash python3 git curl jq sqlite3 systemctl ss awk sed grep \
  sha256sum tar zstd rclone node codex ps df free; do
  have "$command_name" || remediate "missing_command:$command_name"
done

CORE_MISSING=()
for command_name in python3 awk sed grep sha256sum ps df; do
  have "$command_name" || CORE_MISSING+=("$command_name")
done
if ((${#CORE_MISSING[@]})); then
  printf 'REMEDIATION=missing_core_collector_commands:%s\n' \
    "$(IFS=,; echo "${CORE_MISSING[*]}")"
  echo "PREFLIGHT=PASS_WITH_ACTIVATION_PENDING"
  exit 0
fi

for index in 1 2 3; do
  "$SCRIPT_DIR/resource_profile.py" --capture-only \
    >"$CB_PREFLIGHT_TMP/snapshot-$index.json"
done

PROFILE_OUTPUT="$(
  "$SCRIPT_DIR/select-resource-profile.sh" \
    --measurements "$CB_PREFLIGHT_TMP/snapshot-3.json"
)"
ACTIVATION_SAFE="$(
  printf '%s\n' "$PROFILE_OUTPUT" |
    awk -F= '/^CB_RESOURCE_ACTIVATION_SAFE=/{print $2; exit}'
)"
GUARD_STATE="$(
  printf '%s\n' "$PROFILE_OUTPUT" |
    awk -F= '/^CB_RESOURCE_GUARD_STATE=/{print $2; exit}'
)"

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
[[ "$NODE_MAJOR" =~ ^[0-9]+$ ]] || NODE_MAJOR=0
((NODE_MAJOR >= 22)) || remediate "node_major_below_22:$NODE_MAJOR"

machine_id_file=""
for candidate in /etc/machine-id /var/lib/dbus/machine-id; do
  if [[ -r "$candidate" ]]; then
    machine_id_file="$candidate"
    break
  fi
done
if [[ -n "$machine_id_file" ]]; then
  HOST_ID_SHA256="$(sha256sum "$machine_id_file" | awk '{print $1}')"
else
  HOST_ID_SHA256="unavailable"
  remediate "machine_id_unreadable"
fi

sanitize_listener() {
  local protocol="$1"
  local endpoint="$2"
  local port="${endpoint##*:}"
  local scope="non_loopback"
  [[ "$port" =~ ^[0-9]+$ ]] || return 0
  case "$endpoint" in
    127.*:\*|127.*:"$port"|localhost:*|\[::1\]:*)
      scope="loopback"
      ;;
    0.0.0.0:*|\[::\]:*|\*:*)
      scope="wildcard"
      ;;
  esac
  printf 'LISTENER=%s:%s:%s\n' "$protocol" "$port" "$scope"
}

>"$CB_PREFLIGHT_TMP/listeners.raw"
if have ss; then
  while read -r _state _recv _send local_endpoint _peer; do
    sanitize_listener tcp "$local_endpoint"
  done < <(ss -H -lnt 2>/dev/null || true) \
    >>"$CB_PREFLIGHT_TMP/listeners.raw"
  while read -r _state _recv _send local_endpoint _peer; do
    sanitize_listener udp "$local_endpoint"
  done < <(ss -H -lnu 2>/dev/null || true) \
    >>"$CB_PREFLIGHT_TMP/listeners.raw"
else
  remediate "listener_inventory_unavailable"
fi
sort -u "$CB_PREFLIGHT_TMP/listeners.raw" \
  >"$CB_PREFLIGHT_TMP/listeners.txt"

for expected_port in 8765 8780; do
  if grep -Eq "^LISTENER=(tcp|udp):${expected_port}:" \
    "$CB_PREFLIGHT_TMP/listeners.txt"; then
    warn "expected_port_in_use:$expected_port"
  fi
done

filesystem_summary() {
  local label="$1"
  local target="$2"
  [[ -d "$target" ]] || return 0
  local block_line inode_line
  block_line="$(df -Pm "$target" | awk 'END {print $2,$3,$4,$5}')"
  inode_line="$(df -Pi "$target" | awk 'END {print $2,$3,$4,$5}')"
  printf 'FILESYSTEM=%s blocks_mb:%s inodes:%s\n' \
    "$label" "$block_line" "$inode_line"
}

ps -eo comm= 2>/dev/null |
  sed 's#.*/##' |
  sed '/^[[:space:]]*$/d' |
  sort >"$CB_PREFLIGHT_TMP/process-names.txt"
PROCESS_TOTAL="$(wc -l <"$CB_PREFLIGHT_TMP/process-names.txt" | tr -d ' ')"
PROCESS_DISTINCT="$(sort -u "$CB_PREFLIGHT_TMP/process-names.txt" | wc -l | tr -d ' ')"
PROCESS_SET_SHA256="$(
  sort -u "$CB_PREFLIGHT_TMP/process-names.txt" |
    sha256sum |
    awk '{print $1}'
)"
PROCESS_RSS_TOTAL_MB="$(
  ps -eo rss= 2>/dev/null |
    awk '{sum += $1} END {printf "%d", sum/1024}'
)"

known_process_summary() {
  local name="$1"
  local count
  count="$(grep -xc "$name" "$CB_PREFLIGHT_TMP/process-names.txt" || true)"
  printf 'KNOWN_PROCESS=%s:%s\n' "$name" "$count"
}

SYSTEMD_STATE="unavailable"
RUNNING_UNIT_COUNT=0
RUNNING_UNIT_SET_SHA256="unavailable"
STATUS_UNIT_COUNT=0
STATUS_UNIT_SET_SHA256="unavailable"
if have systemctl && systemctl list-units --no-pager >/dev/null 2>&1; then
  SYSTEMD_STATE="readable"
  systemctl list-units --type=service --state=running --no-legend --no-pager |
    awk '{print $1}' |
    sort -u >"$CB_PREFLIGHT_TMP/running-units.txt"
  RUNNING_UNIT_COUNT="$(wc -l <"$CB_PREFLIGHT_TMP/running-units.txt" | tr -d ' ')"
  RUNNING_UNIT_SET_SHA256="$(
    sha256sum "$CB_PREFLIGHT_TMP/running-units.txt" | awk '{print $1}'
  )"
  grep -Ei 'status|uptime|monitor|collector' "$CB_PREFLIGHT_TMP/running-units.txt" |
    sort -u >"$CB_PREFLIGHT_TMP/status-units.txt" || true
  STATUS_UNIT_COUNT="$(wc -l <"$CB_PREFLIGHT_TMP/status-units.txt" | tr -d ' ')"
  STATUS_UNIT_SET_SHA256="$(
    sha256sum "$CB_PREFLIGHT_TMP/status-units.txt" | awk '{print $1}'
  )"
else
  remediate "systemd_inventory_unreadable"
fi

unit_state() {
  local unit="$1"
  local state="inactive"
  if [[ "$SYSTEMD_STATE" == "readable" ]] &&
    systemctl is-active --quiet "$unit" 2>/dev/null; then
    state="active"
  fi
  printf 'KNOWN_UNIT=%s:%s\n' "$unit" "$state"
}

container_state() {
  local runtime="$1"
  if ! have "$runtime"; then
    printf 'CONTAINER_RUNTIME=%s:unavailable:0\n' "$runtime"
    return
  fi
  local count
  if count="$("$runtime" ps --format '{{.ID}}' 2>/dev/null | wc -l | tr -d ' ')"; then
    printf 'CONTAINER_RUNTIME=%s:readable:%s\n' "$runtime" "$count"
  else
    printf 'CONTAINER_RUNTIME=%s:permission_denied:unknown\n' "$runtime"
    remediate "${runtime}_inventory_unreadable"
  fi
}

path_state() {
  local label="$1"
  local target="$2"
  local state="absent"
  [[ -d "$target" ]] && state="directory"
  [[ -e "$target" && ! -d "$target" ]] && state="non_directory"
  printf 'PATH_STATE=%s:%s\n' "$label" "$state"
}

REPORT_PATH="$CB_PREFLIGHT_TMP/report.txt"
{
  echo "SCHEMA_VERSION=1"
  echo "COLLECTOR=cyberboss-read-only-preflight"
  echo "SNAPSHOT_MODE=three_immediate_no_sleep"
  echo "HOST_ID_SHA256=$HOST_ID_SHA256"
  echo "KERNEL_FAMILY=$(uname -s)"
  echo "ARCH=$(uname -m)"
  for index in 1 2 3; do
    echo "SNAPSHOT_${index}_BEGIN"
    cat "$CB_PREFLIGHT_TMP/snapshot-$index.json"
    echo "SNAPSHOT_${index}_END"
  done
  echo "PROFILE_BEGIN"
  printf '%s\n' "$PROFILE_OUTPUT"
  echo "PROFILE_END"
  cat "$CB_PREFLIGHT_TMP/listeners.txt"
  filesystem_summary root /
  filesystem_summary opt /opt
  filesystem_summary var /var
  filesystem_summary srv /srv
  echo "PROCESS_TOTAL=$PROCESS_TOTAL"
  echo "PROCESS_DISTINCT=$PROCESS_DISTINCT"
  echo "PROCESS_SET_SHA256=$PROCESS_SET_SHA256"
  echo "PROCESS_RSS_TOTAL_MB=$PROCESS_RSS_TOTAL_MB"
  for process_name in systemd node codex cyberboss nginx caddy apache2 traefik \
    cloudflared docker podman containerd; do
    known_process_summary "$process_name"
  done
  echo "SYSTEMD_STATE=$SYSTEMD_STATE"
  echo "RUNNING_UNIT_COUNT=$RUNNING_UNIT_COUNT"
  echo "RUNNING_UNIT_SET_SHA256=$RUNNING_UNIT_SET_SHA256"
  echo "STATUS_UNIT_COUNT=$STATUS_UNIT_COUNT"
  echo "STATUS_UNIT_SET_SHA256=$STATUS_UNIT_SET_SHA256"
  for unit_name in nginx.service caddy.service apache2.service traefik.service \
    cloudflared.service docker.service podman.service; do
    unit_state "$unit_name"
  done
  container_state docker
  container_state podman
  path_state app_root /opt/cyberboss-cloud
  path_state state_root /var/lib/cyberboss
  path_state workspace_root /srv/cyberboss-workspaces
  path_state config_root /etc/cyberboss
  echo "NODE_VERSION=$(node --version 2>/dev/null || echo missing)"
  echo "CODEX_VERSION=$(codex --version 2>/dev/null || echo missing)"
  for item in "${WARNINGS[@]}"; do
    echo "WARNING=$item"
  done
  for item in "${REMEDIATIONS[@]}"; do
    echo "REMEDIATION=$item"
  done
  if [[ "$ACTIVATION_SAFE" != "true" || "$GUARD_STATE" == "protect" ]]; then
    echo "PREFLIGHT=HAZARD_BLOCKED"
  elif ((${#REMEDIATIONS[@]})) || ((${#WARNINGS[@]})); then
    echo "PREFLIGHT=PASS_WITH_ACTIVATION_PENDING"
  else
    echo "PREFLIGHT=PASS"
  fi
} >"$REPORT_PATH"

cat "$REPORT_PATH"
if [[ -n "$OUTPUT_PATH" ]]; then
  mkdir -p "$(dirname "$OUTPUT_PATH")"
  temp_output="${OUTPUT_PATH}.tmp.$$"
  cp "$REPORT_PATH" "$temp_output"
  chmod 0640 "$temp_output"
  mv "$temp_output" "$OUTPUT_PATH"
fi
