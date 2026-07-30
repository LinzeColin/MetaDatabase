#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)";cd "$ROOT"
docker compose -f compose.readers.yaml --profile readers --profile karakeep --profile linkwarden --profile archivebox down
