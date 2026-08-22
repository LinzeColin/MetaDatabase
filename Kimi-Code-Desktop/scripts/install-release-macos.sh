#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
DESTINATION="${KIMI_CODE_DESKTOP_DESTINATION:-${HOME}/Applications/Kimi Code.app}"
VERSION="${APP_VERSION:-$(/usr/bin/plutil -extract version raw "$PROJECT_ROOT/package.json")}"
MACHINE_ARCH="$(uname -m)"
ARCH="${MACHINE_ARCH/x86_64/x64}"
TAG="kimi-code-desktop-v$VERSION"
ASSET="Kimi.Code.Desktop-$VERSION-mac-$ARCH.zip"
DOWNLOAD_URL="https://github.com/LinzeColin/MetaDatabase/releases/download/$TAG/$ASSET"

if [ "$(uname -s)" != "Darwin" ] || { [ "$ARCH" != "arm64" ] && [ "$ARCH" != "x64" ]; }; then
  echo "This installer supports arm64 and x64 macOS." >&2
  exit 1
fi

if [ -f "$DESTINATION/Contents/MacOS/Kimi Code" ] && /usr/sbin/lsof -t "$DESTINATION/Contents/MacOS/Kimi Code" >/dev/null 2>&1; then
  echo "Kimi Code is running. Use Cmd+Q after current tasks finish, then run this installer again." >&2
  exit 1
fi

TEMP_ROOT="$(mktemp -d /tmp/kimi-code-desktop-release.XXXXXX)"
STAGE_ROOT=""
cleanup() {
  find "$TEMP_ROOT" -depth -delete
  if [ -n "$STAGE_ROOT" ] && [ -d "$STAGE_ROOT" ]; then find "$STAGE_ROOT" -depth -delete; fi
}
trap cleanup EXIT
ARCHIVE="$TEMP_ROOT/$ASSET"
/usr/bin/curl --fail --location --output "$ARCHIVE" "$DOWNLOAD_URL"
/usr/bin/ditto -x -k "$ARCHIVE" "$TEMP_ROOT/unpacked"

SOURCE_APP="$TEMP_ROOT/unpacked/Kimi Code.app"
if [ ! -d "$SOURCE_APP" ]; then
  echo "Downloaded archive did not contain Kimi Code.app." >&2
  exit 1
fi

ACTUAL_ID="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$SOURCE_APP/Contents/Info.plist")"
ACTUAL_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$SOURCE_APP/Contents/Info.plist")"
if [ "$ACTUAL_ID" != "com.electron.kimi-code" ] || [ "$ACTUAL_VERSION" != "$VERSION" ]; then
  echo "Downloaded app identity or version did not match the requested Kimi Code release." >&2
  exit 1
fi
if ! /usr/bin/codesign --verify --deep --strict "$SOURCE_APP"; then
  echo "Downloaded app did not pass macOS code-integrity verification." >&2
  exit 1
fi
CODE_ID="$(/usr/bin/codesign -dv --verbose=4 "$SOURCE_APP" 2>&1 | /usr/bin/awk -F= '/^Identifier=/{print $2; exit}')"
if [ "$CODE_ID" != "com.electron.kimi-code" ]; then
  echo "Downloaded app code identity did not match Kimi Code Desktop." >&2
  exit 1
fi

DESTINATION_PARENT="$(dirname "$DESTINATION")"
mkdir -p "$DESTINATION_PARENT"
STAGE_ROOT="$(mktemp -d "$DESTINATION_PARENT/.kimi-code-release-update.XXXXXX")"
STAGED_APP="$STAGE_ROOT/Kimi Code.app"
ROLLBACK="${HOME}/.kimi-code/desktop-updates/rollback/${VERSION}-$(date +%s)/Kimi Code.app.rollback"
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
echo "Installed Kimi Code Desktop $VERSION. Future app updates follow the official Kimi Code version line."
