#!/bin/bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
APP="${DSH_DESKTOP_APP:-${HOME}/Applications/DSH Desktop.app}"
PATCH_ROOT="${HOME}/.dsh/_patches"
UPDATE_ROOT="${HOME}/.dsh/desktop-updates"
ICON_SOURCE=""

if [ "${1:-}" != "--apply" ]; then
  echo "Preview only. This installs the HarnessUI bridge without starting or restarting DSH Desktop."
  echo "Re-run with --apply after fully quitting DSH Desktop. Optionally add: --icon /absolute/path/icon.icns"
  exit 0
fi
shift
if [ "${1:-}" = "--icon" ]; then
  ICON_SOURCE="${2:-}"
fi

if [ ! -d "$APP" ]; then
  echo "DSH Desktop.app was not found: $APP" >&2
  exit 1
fi
if /usr/sbin/lsof -t "$APP/Contents/MacOS/DSH Desktop" >/dev/null 2>&1; then
  echo "DSH Desktop is running. Quit it with Cmd+Q, then run this installer again." >&2
  exit 1
fi

/bin/mkdir -p "$PATCH_ROOT" "$UPDATE_ROOT/staging"
/bin/cp "$SCRIPT_DIR/patch-dsh-runtime.py" "$PATCH_ROOT/patch-dsh-runtime.py"
/bin/cp "$SCRIPT_DIR/install-dsh-update.py" "$PATCH_ROOT/install-dsh-update.py"
/bin/chmod 700 "$PATCH_ROOT/patch-dsh-runtime.py" "$PATCH_ROOT/install-dsh-update.py"

if [ -n "$ICON_SOURCE" ]; then
  case "$ICON_SOURCE" in
    /*.icns) ;;
    *) echo "The icon must be an absolute .icns path." >&2; exit 1 ;;
  esac
  /bin/mkdir -p "${HOME}/.dsh/personalization/dsh-desktop"
  /bin/cp "$ICON_SOURCE" "${HOME}/.dsh/personalization/dsh-desktop/icon.icns"
  /usr/bin/sips -s format png "$ICON_SOURCE" --out "${HOME}/.dsh/personalization/dsh-desktop/icon.png" >/dev/null
fi

STAGE_ROOT="$(mktemp -d "$UPDATE_ROOT/staging/.dsh-bridge.XXXXXX")"
STAGED_APP="$STAGE_ROOT/$(basename "$APP")"
ROLLBACK="$UPDATE_ROOT/rollback/bridge-$(date +%s)/$(basename "$APP").rollback"
/usr/bin/ditto "$APP" "$STAGED_APP"
/usr/bin/find "$STAGED_APP" -type d -exec /bin/chmod u+rwx {} +
/usr/bin/find "$STAGED_APP" -type f -exec /bin/chmod u+rw {} +
/usr/bin/python3 "$PATCH_ROOT/patch-dsh-runtime.py" --app "$STAGED_APP" --no-backup
/usr/bin/codesign --force --deep --sign - \
  --identifier ai.deepseek.dsh.desktop \
  --requirements '=designated => identifier "ai.deepseek.dsh.desktop"' \
  "$STAGED_APP"
node "$PROJECT_ROOT/scripts/install-dsh.mjs" --apply
/bin/mkdir -p "$(dirname "$ROLLBACK")"
/bin/mv "$APP" "$ROLLBACK"
if ! /bin/mv "$STAGED_APP" "$APP"; then
  /bin/mv "$ROLLBACK" "$APP"
  exit 1
fi
/bin/rmdir "$STAGE_ROOT" || true

echo "Installed without launching DSH Desktop: $APP"
echo "Future official DSH updates keep ~/.dsh, ~/.harness-ui, the external icon and HarnessUI state in place."
