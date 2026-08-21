#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
echo "The private community version line is retired; using the canonical Harness UI release installer."
exec "$SCRIPT_DIR/install-release-macos.sh" "$@"
