#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$ROOT/scripts/run_tests.py" --root "$ROOT" --timeout-per-file "${SIGNAL_LATTICE_TEST_FILE_TIMEOUT:-120}"
