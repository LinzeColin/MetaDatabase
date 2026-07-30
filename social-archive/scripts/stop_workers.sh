#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
docker compose -f compose.yaml -f compose.workers.yaml --profile domestic-stable --profile douk-experimental stop xhs-worker ks-worker douk-worker || true
printf '东方平台 Worker 已停止；Social Archive 核心和通用保存不受影响。\n'
