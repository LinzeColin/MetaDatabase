#!/usr/bin/env bash
set -Eeuo pipefail

WRITE_PATH=""
DROPIN_PATH=""
while (($#)); do
  case "$1" in
    --write) WRITE_PATH="${2:-}"; shift 2 ;;
    --systemd-dropin) DROPIN_PATH="${2:-}"; shift 2 ;;
    *) echo "PROFILE=FAIL unknown_arg:$1"; exit 2 ;;
  esac
done

[[ -r /proc/meminfo ]] || { echo 'PROFILE=FAIL proc_meminfo_unreadable'; exit 2; }
TOTAL_MB="$(( $(awk '/MemTotal:/ {print $2}' /proc/meminfo) / 1024 ))"
AVAIL_MB="$(( $(awk '/MemAvailable:/ {print $2}' /proc/meminfo) / 1024 ))"
FREE_DISK_MB="$(df -Pm / | awk 'NR==2 {print $4}')"
CPU_COUNT="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1)"

if (( TOTAL_MB < 2048 || AVAIL_MB < 768 || FREE_DISK_MB < 4096 )); then
  PROFILE="constrained"
  MEMORY_HIGH="768M"
  MEMORY_MAX="1152M"
  TASKS_MAX="256"
  QUEUE_LIMIT="20"
  WORKSPACE_BYTES="4294967296"
  LOG_BYTES="157286400"
  SNAPSHOT_BYTES="536870912"
elif (( TOTAL_MB < 6144 || AVAIL_MB < 2048 || FREE_DISK_MB < 16384 )); then
  PROFILE="tiny"
  MEMORY_HIGH="1100M"
  MEMORY_MAX="1600M"
  TASKS_MAX="384"
  QUEUE_LIMIT="50"
  WORKSPACE_BYTES="8589934592"
  LOG_BYTES="314572800"
  SNAPSHOT_BYTES="1073741824"
else
  PROFILE="standard"
  MEMORY_HIGH="1800M"
  MEMORY_MAX="2600M"
  TASKS_MAX="512"
  QUEUE_LIMIT="100"
  WORKSPACE_BYTES="12884901888"
  LOG_BYTES="536870912"
  SNAPSHOT_BYTES="2147483648"
fi

CONTENT="$(cat <<PROFILE_ENV
# Generated from live host measurements; safe to regenerate.
CB_RESOURCE_PROFILE=$PROFILE
CB_MEASURED_TOTAL_MEMORY_MB=$TOTAL_MB
CB_MEASURED_AVAILABLE_MEMORY_MB=$AVAIL_MB
CB_MEASURED_FREE_DISK_MB=$FREE_DISK_MB
CB_MEASURED_CPU_COUNT=$CPU_COUNT
CB_SYSTEMD_MEMORY_HIGH=$MEMORY_HIGH
CB_SYSTEMD_MEMORY_MAX=$MEMORY_MAX
CB_SYSTEMD_TASKS_MAX=$TASKS_MAX
CB_QUEUE_LIMIT=$QUEUE_LIMIT
CB_MAX_WORKSPACE_BYTES=$WORKSPACE_BYTES
CB_MAX_LOG_BYTES=$LOG_BYTES
CB_MAX_LOCAL_SNAPSHOT_BYTES=$SNAPSHOT_BYTES
PROFILE_ENV
)"

if [[ -n "$DROPIN_PATH" ]]; then
  [[ "$DROPIN_PATH" == /* ]] || { echo 'PROFILE=FAIL dropin_path_must_be_absolute'; exit 2; }
  install -d -m 0755 "$(dirname "$DROPIN_PATH")"
  drop_tmp="${DROPIN_PATH}.tmp.$$"
  cat > "$drop_tmp" <<DROPIN
[Service]
MemoryHigh=$MEMORY_HIGH
MemoryMax=$MEMORY_MAX
TasksMax=$TASKS_MAX
DROPIN
  chmod 0644 "$drop_tmp"
  mv "$drop_tmp" "$DROPIN_PATH"
fi

if [[ -n "$WRITE_PATH" ]]; then
  [[ "$WRITE_PATH" == /* ]] || { echo 'PROFILE=FAIL write_path_must_be_absolute'; exit 2; }
  install -d -m 0750 "$(dirname "$WRITE_PATH")"
  tmp="${WRITE_PATH}.tmp.$$"
  printf '%s\n' "$CONTENT" > "$tmp"
  chmod 0640 "$tmp"
  mv "$tmp" "$WRITE_PATH"
fi

printf '%s\n' "$CONTENT"
echo "PROFILE=PASS selected=$PROFILE"
