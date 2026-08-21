#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
DESTINATION="${HARNESS_UI_DESTINATION:-${HOME}/Applications/Harness UI.app}"
VERSION="${APP_VERSION:-$(/usr/bin/plutil -extract version raw "$PROJECT_ROOT/package.json")}"
TAG="harness-ui-v$VERSION"
ASSET="Harness-UI-$VERSION-mac-arm64.zip"
DOWNLOAD_URL="https://github.com/LinzeColin/MetaDatabase/releases/download/$TAG/$ASSET"

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "This installer supports Apple Silicon macOS only." >&2
  exit 1
fi

if [ -f "$DESTINATION/Contents/MacOS/Harness UI" ] && /usr/sbin/lsof -t "$DESTINATION/Contents/MacOS/Harness UI" >/dev/null 2>&1; then
  echo "Harness UI is running. Quit it, then run this installer again." >&2
  exit 1
fi

TEMP_ROOT="$(mktemp -d /tmp/harness-ui-release.XXXXXX)"
STAGE_ROOT=""
cleanup() {
  find "$TEMP_ROOT" -depth -delete
  if [ -n "$STAGE_ROOT" ] && [ -d "$STAGE_ROOT" ]; then find "$STAGE_ROOT" -depth -delete; fi
}
trap cleanup EXIT
ARCHIVE="$TEMP_ROOT/$ASSET"
/usr/bin/curl --fail --location --output "$ARCHIVE" "$DOWNLOAD_URL"
/usr/bin/ditto -x -k "$ARCHIVE" "$TEMP_ROOT/unpacked"

SOURCE_APP="$TEMP_ROOT/unpacked/Harness UI.app"
if [ ! -d "$SOURCE_APP" ]; then
  echo "Downloaded archive did not contain Harness UI.app." >&2
  exit 1
fi

ACTUAL_ID="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$SOURCE_APP/Contents/Info.plist")"
ACTUAL_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$SOURCE_APP/Contents/Info.plist")"
if [ "$ACTUAL_ID" != "com.linzecolin.harnessui" ] || [ "$ACTUAL_VERSION" != "$VERSION" ]; then
  echo "Downloaded app identity or version did not match the requested Harness UI release." >&2
  exit 1
fi
/usr/bin/codesign --verify --deep --strict "$SOURCE_APP"

DESTINATION_PARENT="$(dirname "$DESTINATION")"
mkdir -p "$DESTINATION_PARENT"
STAGE_ROOT="$(mktemp -d "$DESTINATION_PARENT/.harness-ui-release-update.XXXXXX")"
STAGED_APP="$STAGE_ROOT/Harness UI.app"
ROLLBACK="${HOME}/.harness-ui/desktop-updates/rollback/${VERSION}-$(date +%s)/Harness UI.app"
ditto "$SOURCE_APP" "$STAGED_APP"
if [ -e "$DESTINATION" ]; then
  mkdir -p "$(dirname "$ROLLBACK")"
  mv "$DESTINATION" "$ROLLBACK"
fi
if ! mv "$STAGED_APP" "$DESTINATION"; then
  if [ -e "$ROLLBACK" ] && [ ! -e "$DESTINATION" ]; then mv "$ROLLBACK" "$DESTINATION"; fi
  exit 1
fi
rmdir "$STAGE_ROOT"
STAGE_ROOT=""

echo "Installed without launching: $DESTINATION"
if [ -e "$ROLLBACK" ]; then echo "Previous app preserved at: $ROLLBACK"; fi
echo "Installed Harness UI $VERSION. Use its tray/menu-bar update button for future releases."
