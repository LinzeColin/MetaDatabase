#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -x .venv/bin/python ]] || { printf '请先运行 bash scripts/install.sh\n' >&2; exit 2; }
.venv/bin/python scripts/backup.py "$@"
