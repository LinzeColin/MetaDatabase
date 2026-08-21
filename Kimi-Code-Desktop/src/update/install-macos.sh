#!/bin/sh
set -eu

app_pid="$1"
archive="$2"
target="$3"
rollback="$4"
bundle_id="$5"
version="$6"
updates_root="$(/usr/bin/dirname "$0")"
pending_receipt="$updates_root/pending-update-result.json"
stage=""
installed=0

write_receipt() {
  status="$1"
  detail="$2"
  temporary="$pending_receipt.tmp"
  /usr/bin/printf '{\n  "version": 1,\n  "status": "%s",\n  "desktopVersion": "%s",\n  "detail": "%s",\n  "updatedAt": "%s"\n}\n' \
    "$status" "$version" "$detail" "$(/bin/date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$temporary"
  /bin/mv "$temporary" "$pending_receipt"
}

finish() {
  code="$?"
  trap - EXIT
  if [ "$installed" -ne 1 ]; then
    write_receipt "failed" "安装未完成，旧版已重新打开；配置、会话、皮肤和素材均未修改。"
    if [ -e "$target" ]; then /usr/bin/open "$target" >/dev/null 2>&1 || true; fi
  fi
  if [ -n "$stage" ] && [ -d "$stage" ]; then
    case "$stage" in
      "${TMPDIR:-/tmp}"/kimi-code-update.*) /bin/rm -rf "$stage" ;;
    esac
  fi
  exit "$code"
}

trap finish EXIT

case "$target" in
  /*.app) ;;
  *) exit 20 ;;
esac
case "$archive" in
  /*.zip) ;;
  *) exit 21 ;;
esac

attempt=0
while /bin/kill -0 "$app_pid" 2>/dev/null; do
  attempt=$((attempt + 1))
  [ "$attempt" -le 240 ] || exit 22
  /bin/sleep 0.5
done

stage="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/kimi-code-update.XXXXXX")"
/usr/bin/ditto -x -k "$archive" "$stage"
candidate="$(/usr/bin/find "$stage" -maxdepth 2 -type d -name '*.app' -print -quit)"
[ -n "$candidate" ] || exit 23

actual_id="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$candidate/Contents/Info.plist")"
[ "$actual_id" = "$bundle_id" ] || exit 24
actual_version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$candidate/Contents/Info.plist")"
[ "$actual_version" = "$version" ] || exit 26
/usr/bin/codesign --verify --deep --strict "$candidate"
/usr/sbin/spctl --assess --type execute "$candidate"

/bin/mkdir -p "$(/usr/bin/dirname "$rollback")"
if [ -e "$target" ]; then /bin/mv "$target" "$rollback"; fi
if ! /bin/mv "$candidate" "$target"; then
  if [ -e "$rollback" ] && [ ! -e "$target" ]; then /bin/mv "$rollback" "$target"; fi
  exit 25
fi
write_receipt "installed" "应用本体已更新；配置、会话、皮肤、素材与外置图标保持原位。"
installed=1
/usr/bin/open "$target" >/dev/null 2>&1 || true
