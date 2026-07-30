#!/usr/bin/env bash
set -euo pipefail
MIN_YEAR=2025
MIN_MONTH=4
if ! command -v cloudflared >/dev/null 2>&1; then
  echo '{"state":"BLOCKED","reason":"CLOUDFLARED_NOT_INSTALLED","environment_bound_reason":"Install cloudflared from the official Cloudflare package repository or provide a verified binary."}'
  exit 2
fi
VERSION_RAW="$(cloudflared --version 2>/dev/null || true)"
VERSION="$(printf '%s' "$VERSION_RAW" | grep -Eo '[0-9]{4}\.[0-9]+\.[0-9]+' | head -1)"
[[ -n "$VERSION" ]] || { echo '{"state":"BLOCKED","reason":"CLOUDFLARED_VERSION_UNREADABLE"}'; exit 2; }
YEAR="${VERSION%%.*}"
REST="${VERSION#*.}"
MONTH="${REST%%.*}"
if (( YEAR < MIN_YEAR || (YEAR == MIN_YEAR && MONTH < MIN_MONTH) )); then
  printf '{"state":"BLOCKED","reason":"CLOUDFLARED_TOO_OLD","version":"%s","minimum":"2025.4.0"}\n' "$VERSION"
  exit 2
fi
printf '{"state":"PASS","version":"%s","token_file_supported":true}\n' "$VERSION"
