#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
DESTINATION="${HARNESS_UI_DESTINATION:-${HOME}/Applications/Harness UI.app}"
VERSION="${COMMUNITY_VERSION:-$(/usr/bin/plutil -extract version raw "$PROJECT_ROOT/package.json")}"
TAG="harness-ui-community-v$VERSION"
ASSET="Harness-UI-$VERSION-macos-arm64-NOT-NOTARIZED.zip"
DOWNLOAD_URL="https://github.com/LinzeColin/MetaDatabase/releases/download/$TAG/$ASSET"

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "This installer supports Apple Silicon macOS only." >&2
  exit 1
fi

if [ -e "$DESTINATION" ]; then
  echo "Destination already exists; nothing was changed: $DESTINATION" >&2
  exit 1
fi

TEMP_ROOT="$(mktemp -d /tmp/harness-ui-community.XXXXXX)"
trap 'find "$TEMP_ROOT" -depth -delete' EXIT
ARCHIVE="$TEMP_ROOT/$ASSET"
/usr/bin/curl --fail --location --output "$ARCHIVE" "$DOWNLOAD_URL"
/usr/bin/ditto -x -k "$ARCHIVE" "$TEMP_ROOT/unpacked"

SOURCE_APP="$TEMP_ROOT/unpacked/Harness UI.app"
if [ ! -d "$SOURCE_APP" ]; then
  echo "Downloaded archive did not contain Harness UI.app." >&2
  exit 1
fi

mkdir -p "$(dirname "$DESTINATION")"
ditto "$SOURCE_APP" "$DESTINATION"

echo "Installed without launching: $DESTINATION"
echo "This community build is ad-hoc signed only and is not Apple-notarized."
