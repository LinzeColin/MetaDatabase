#!/bin/sh
set -eu

if [ "${1:-}" != "--apply" ]; then
  echo "Preview only. Re-run with --apply to install or update the loopback HarnessUI service."
  echo "Kimi Code and DSH are not restarted; only the HarnessUI service is reloaded."
  exit 0
fi

script_dir="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
project_root="$(dirname "$script_dir")"
runtime_root="${HARNESS_UI_ROOT:-$HOME/.harness-ui}"
mount_point="${HARNESS_UI_MOUNT_POINT:-/Volumes/share}"
smb_url="${HARNESS_UI_SMB_URL:-smb://GUEST@192.168.0.1/share}"
source_root="${HARNESS_UI_SOURCE:-$mount_point/03_资料库/MetaData/HarnessUI}"
volume_id_file="${HARNESS_UI_VOLUME_ID_FILE:-$mount_point/00_AgentControl/NAS_VOLUME_ID.md}"
volume_id="${HARNESS_UI_VOLUME_ID:-LINZE_EXTERNAL_NAS_SHARE_V1_20260822}"
agents_root="$HOME/Library/LaunchAgents"
assets_agent="$agents_root/com.harnessui.assets.plist"
smb_agent="$agents_root/com.harnessui.smb.plist"
uid="$(id -u)"

escape_sed() {
  printf '%s' "$1" | /usr/bin/sed 's/[&|]/\\&/g'
}

render() {
  template="$1"
  destination="$2"
  temporary="$destination.tmp"
  /usr/bin/sed \
    -e "s|__HARNESS_UI_ROOT__|$(escape_sed "$runtime_root")|g" \
    -e "s|__HARNESS_UI_SOURCE__|$(escape_sed "$source_root")|g" \
    -e "s|__HARNESS_UI_MOUNT__|$(escape_sed "$mount_point")|g" \
    -e "s|__HARNESS_UI_SMB_URL__|$(escape_sed "$smb_url")|g" \
    -e "s|__HARNESS_UI_VOLUME_ID_FILE__|$(escape_sed "$volume_id_file")|g" \
    -e "s|__HARNESS_UI_VOLUME_ID__|$(escape_sed "$volume_id")|g" \
    "$template" > "$temporary"
  /usr/bin/plutil -lint "$temporary" >/dev/null
  /bin/mv "$temporary" "$destination"
}

/bin/mkdir -p "$runtime_root/web" "$runtime_root/master" "$agents_root"
/usr/bin/install -m 700 "$script_dir/harness_service.py" "$runtime_root/harness_service.py"
/usr/bin/install -m 700 "$script_dir/mount-harness-smb.sh" "$runtime_root/mount-harness-smb.sh"
for mount_helper_candidate in \
  "${HARNESS_UI_MOUNT_HELPER_SOURCE:-}" \
  "$HOME/Applications/Harness UI.app/Contents/Resources/HarnessSMBMounter" \
  "/Applications/Harness UI.app/Contents/Resources/HarnessSMBMounter"
do
  if [ -n "$mount_helper_candidate" ] && [ -x "$mount_helper_candidate" ]; then
    /usr/bin/install -m 700 "$mount_helper_candidate" "$runtime_root/harness-smb-mounter"
    break
  fi
done
/usr/bin/install -m 600 "$project_root/web/index.html" "$runtime_root/web/index.html"
/usr/bin/install -m 600 "$project_root/web/app.js" "$runtime_root/web/app.js"
/usr/bin/install -m 600 "$project_root/web/app.css" "$runtime_root/web/app.css"
render "$script_dir/com.harnessui.assets.plist" "$assets_agent"
render "$script_dir/com.harnessui.smb.plist" "$smb_agent"

/bin/launchctl bootout "gui/$uid/com.harnessui.assets" >/dev/null 2>&1 || true
/bin/launchctl bootout "gui/$uid/com.harnessui.smb" >/dev/null 2>&1 || true
/bin/launchctl enable "gui/$uid/com.harnessui.smb"
/bin/launchctl enable "gui/$uid/com.harnessui.assets"
/bin/launchctl bootstrap "gui/$uid" "$smb_agent"
/bin/launchctl bootstrap "gui/$uid" "$assets_agent"

harness_service_ready=0
harness_attempts_remaining=40
while [ "$harness_attempts_remaining" -gt 0 ]; do
  if /usr/bin/curl --silent --fail --max-time 1 "http://127.0.0.1:3099/state.json" >/dev/null 2>&1; then
    harness_service_ready=1
    break
  fi
  harness_attempts_remaining=$((harness_attempts_remaining - 1))
  /bin/sleep 0.25
done
if [ "$harness_service_ready" -ne 1 ]; then
  echo "HarnessUI service did not become ready on 127.0.0.1:3099." >&2
  exit 1
fi

echo "HarnessUI service installed at $runtime_root and listening on 127.0.0.1:3099."
