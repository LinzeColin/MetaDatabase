#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${SIGNAL_LATTICE_PYTHON:-python3}"
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
  for candidate in python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi
"$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3, 11), "Signal Lattice requires Python >= 3.11"'
PYTHONWARNINGS=error PYTHONPATH="$ROOT/src" "$PYTHON_BIN" -m unittest discover -s "$ROOT/tests" -v
