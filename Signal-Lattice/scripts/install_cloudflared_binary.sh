#!/usr/bin/env bash
set -euo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo ROOT_REQUIRED >&2; exit 2; }
VERSION="${CLOUDFLARED_VERSION:-2026.7.3}"
DEST="/usr/local/bin/cloudflared"
case "$(uname -m)" in
  x86_64|amd64) ASSET="cloudflared-linux-amd64"; EXPECTED_SHA256="9d71c677db00134c1bd4144b7783486b654ad281b1ea62b4972098d19f770f17" ;;
  aarch64|arm64) ASSET="cloudflared-linux-arm64"; EXPECTED_SHA256="65259e652a7bea08bf5df603233ab22b8bf3116af8df9f9206209af6a1b955c0" ;;
  *) echo UNSUPPORTED_ARCHITECTURE >&2; exit 2 ;;
esac
[[ "$VERSION" == "2026.7.3" ]] || { echo UNPINNED_CLOUDFLARED_VERSION >&2; exit 2; }
existing="$(command -v cloudflared 2>/dev/null || true)"
if [[ -n "$existing" ]]; then
  v="$($existing --version 2>/dev/null || true)"
  parsed="$(printf '%s' "$v" | grep -Eo '[0-9]{4}\.[0-9]+\.[0-9]+' | head -1 || true)"
  if [[ -n "$parsed" ]]; then
    y="${parsed%%.*}"; rest="${parsed#*.}"; m="${rest%%.*}"
    if (( y > 2025 || (y == 2025 && m >= 4) )); then
      if [[ "$existing" != "$DEST" ]]; then ln -sfn "$existing" "$DEST"; fi
      python3 - "$DEST" "$parsed" <<'PY'
import json,sys
print(json.dumps({"state":"PASS","action":"REUSED","binary":sys.argv[1],"version":sys.argv[2]},sort_keys=True))
PY
      exit 0
    fi
  fi
fi
command -v curl >/dev/null || { echo CURL_REQUIRED >&2; exit 2; }
tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT
url="https://github.com/cloudflare/cloudflared/releases/download/${VERSION}/${ASSET}"
curl --fail --location --proto '=https' --tlsv1.2 --retry 3 --output "$tmp" "$url"
actual="$(sha256sum "$tmp" | awk '{print $1}')"
[[ "$actual" == "$EXPECTED_SHA256" ]] || { echo CLOUDFLARED_SHA256_MISMATCH >&2; exit 2; }
install -m 0755 -o root -g root "$tmp" "$DEST"
"$DEST" --version >/dev/null
python3 - "$DEST" "$VERSION" "$actual" <<'PY'
import json,sys
print(json.dumps({"state":"PASS","action":"INSTALLED","binary":sys.argv[1],"version":sys.argv[2],"sha256":sys.argv[3]},sort_keys=True))
PY
