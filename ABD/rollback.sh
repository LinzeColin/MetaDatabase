#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

if [ -n "${ABD_PYTHON:-}" ]; then
    PYTHON_BIN=$ABD_PYTHON
elif [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN=$SCRIPT_DIR/.venv/bin/python
elif command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python3.12)
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python3)
else
    echo "rollback blocked: Python 3.12 runtime not found" >&2
    exit 78
fi

if [ ! -x "$PYTHON_BIN" ] || ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if (3, 12) <= sys.version_info[:2] < (3, 13) else 1)' >/dev/null 2>&1; then
    echo "rollback blocked: ABD requires an executable Python 3.12 runtime" >&2
    exit 78
fi

exec "$PYTHON_BIN" -m abd_acceptance.release_control rollback "$@"
