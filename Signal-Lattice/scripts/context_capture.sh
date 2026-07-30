#!/usr/bin/env bash
set -euo pipefail
umask 077
OUT="${1:-/tmp/signal-lattice-context.json}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$ROOT/scripts/context_capture.py" --output "$OUT"
