#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
MAC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
PROJECT_ROOT="$(cd "$MAC_ROOT/.." && pwd -P)"
CONFIGURATION="${CONFIGURATION:-release}"
ARCHITECTURE="${ARCHITECTURE:-arm64}"
APP_VERSION="${APP_VERSION:-1.0.0}"
OUTPUT_ROOT="$PROJECT_ROOT/dist/macos-$ARCHITECTURE"
APP="$OUTPUT_ROOT/Harness UI.app"

cd "$MAC_ROOT"
swift build -c "$CONFIGURATION" --arch "$ARCHITECTURE"
BIN_DIR="$(swift build -c "$CONFIGURATION" --arch "$ARCHITECTURE" --show-bin-path)"

rm -rf "$OUTPUT_ROOT"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/web"
cp "$BIN_DIR/HarnessUIApp" "$APP/Contents/MacOS/Harness UI"
cp "$MAC_ROOT/Info.plist" "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "$APP/Contents/Info.plist"
cp "$PROJECT_ROOT/web/index.html" "$PROJECT_ROOT/web/app.css" "$PROJECT_ROOT/web/app.js" "$APP/Contents/Resources/web/"
cp "$PROJECT_ROOT/config/labels.seed.json" "$APP/Contents/Resources/labels.seed.json"

ICONSET="$OUTPUT_ROOT/AppIcon.iconset"
mkdir -p "$ICONSET"
sips -s format png "$PROJECT_ROOT/assets/icon.svg" --out "$OUTPUT_ROOT/icon.png" >/dev/null
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$OUTPUT_ROOT/icon.png" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" "$OUTPUT_ROOT/icon.png" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"
rm -rf "$ICONSET" "$OUTPUT_ROOT/icon.png"
codesign --force --deep --sign - \
  --identifier com.linzecolin.harnessui \
  --requirements '=designated => identifier "com.linzecolin.harnessui"' \
  "$APP"

echo "app=$APP"
