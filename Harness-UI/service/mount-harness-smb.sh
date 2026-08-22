#!/bin/sh
set -eu

mount_point="${HARNESS_UI_MOUNT_POINT:-/Volumes/share}"
share_url="${HARNESS_UI_SMB_URL:-smb://GUEST@192.168.0.1/share}"
volume_id_file="${HARNESS_UI_VOLUME_ID_FILE:-$mount_point/00_AgentControl/NAS_VOLUME_ID.md}"
volume_id="${HARNESS_UI_VOLUME_ID:-LINZE_EXTERNAL_NAS_SHARE_V1_20260822}"

unset DEEPSEEK_API_KEY OPENCHATCUT_MCP_TOKEN

authoritative_share_is_ready() {
  share_state="$(/usr/bin/smbutil statshares -m "$mount_point" -f JSON 2>/dev/null)" || return 1
  printf '%s\n' "$share_state" | /usr/bin/grep -F '"SERVER_NAME" : "192.168.0.1"' >/dev/null || return 1
  printf '%s\n' "$share_state" | /usr/bin/grep -F '"share_name" : "share"' >/dev/null || return 1
  [ -e "$volume_id_file" ] || return 1

  # A background LaunchAgent can inspect an SMB mount while macOS TCC denies
  # reading bytes from Network Volumes. In that case the exact smbutil
  # server/share identity plus marker existence is authoritative. Whenever
  # the marker is readable, its value must still match exactly.
  if detected_volume_id="$(/usr/bin/sed -n '1p' "$volume_id_file" 2>/dev/null)"; then
    [ "$detected_volume_id" = "$volume_id" ] || return 1
  fi
  return 0
}

if authoritative_share_is_ready; then
  exit 0
fi

if [ -e "$mount_point" ]; then
  echo "Canonical SMB path is occupied by an unverified filesystem: $mount_point" >&2
  exit 70
fi

/usr/bin/osascript - "$share_url" >/dev/null <<'APPLESCRIPT'
on run arguments
  mount volume (item 1 of arguments)
end run
APPLESCRIPT
if authoritative_share_is_ready; then
  exit 0
fi

echo "Canonical SMB share did not become ready at $mount_point" >&2
exit 71
