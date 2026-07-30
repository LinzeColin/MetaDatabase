#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONWARNINGS=error PYTHONPATH="$ROOT/src" python3 -m unittest discover -s "$ROOT/tests" -v
