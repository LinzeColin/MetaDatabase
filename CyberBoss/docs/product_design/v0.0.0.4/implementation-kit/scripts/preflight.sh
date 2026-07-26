#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORTS=(8765 8780)
REMEDIATIONS=()
WARNINGS=()

have() { command -v "$1" >/dev/null 2>&1; }
remediate() { REMEDIATIONS+=("$1"); }
warn() { WARNINGS+=("$1"); }

for cmd in bash git curl jq sqlite3 systemctl ss awk sed grep sha256sum tar zstd rclone node codex; do
  have "$cmd" || remediate "missing_command:$cmd"
done

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
[[ "$NODE_MAJOR" =~ ^[0-9]+$ ]] || NODE_MAJOR=0
(( NODE_MAJOR >= 22 )) || remediate "node_major_below_22:$NODE_MAJOR"

if [[ -r /proc/meminfo ]]; then
  AVAIL_MB="$(( $(awk '/MemAvailable:/ {print $2}' /proc/meminfo) / 1024 ))"
  TOTAL_MB="$(( $(awk '/MemTotal:/ {print $2}' /proc/meminfo) / 1024 ))"
else
  AVAIL_MB=0; TOTAL_MB=0; remediate 'proc_meminfo_unreadable'
fi
FREE_DISK_MB="$(df -Pm / | awk 'NR==2 {print $4}')"
DISK_USED="$(df -P / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')"
INODE_USED="$(df -Pi / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')"

for port in "${PORTS[@]}"; do
  if have ss && ss -lntH "sport = :$port" 2>/dev/null | grep -q .; then
    warn "port_in_use:$port"
  fi
done

if pgrep -af 'cyberboss|app-server.*8765' >"/tmp/cyberboss-preflight-processes.$$" 2>/dev/null; then
  warn "existing_related_processes_detected:/tmp/cyberboss-preflight-processes.$$"
else
  rm -f "/tmp/cyberboss-preflight-processes.$$"
fi

PROFILE_OUTPUT="$("$SCRIPT_DIR/select-resource-profile.sh")"
printf '%s\n' "$PROFILE_OUTPUT"
printf 'HOST=%s\n' "$(hostname -f 2>/dev/null || hostname)"
printf 'TOTAL_MEMORY_MB=%s\nAVAILABLE_MEMORY_MB=%s\nFREE_DISK_MB=%s\n' "$TOTAL_MB" "$AVAIL_MB" "$FREE_DISK_MB"
printf 'DISK_USED_PERCENT=%s\nINODE_USED_PERCENT=%s\n' "$DISK_USED" "$INODE_USED"
printf 'NODE_VERSION=%s\nCODEX_VERSION=%s\n' "$(node --version 2>/dev/null || echo missing)" "$(codex --version 2>/dev/null || echo missing)"
for item in "${WARNINGS[@]}"; do printf 'WARNING=%s\n' "$item"; done
for item in "${REMEDIATIONS[@]}"; do printf 'REMEDIATION=%s\n' "$item"; done

if ((${#REMEDIATIONS[@]})); then
  echo 'PREFLIGHT=READY_TO_REMEDIATE'
else
  echo 'PREFLIGHT=PASS'
fi
# Missing ordinary dependencies/resources are actionable work, not a global development wait node.
exit 0
