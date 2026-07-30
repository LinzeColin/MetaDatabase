#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mode="${1:-stable}"
mkdir -p runtime/vendor-output/xhs runtime/vendor-output/kuaishou runtime/vendor-output/douk
case "$mode" in
  stable)
    docker compose -f compose.yaml -f compose.workers.yaml --profile domestic-stable up -d xhs-worker ks-worker
    services=(xhs-worker ks-worker)
    ;;
  xhs)
    docker compose -f compose.yaml -f compose.workers.yaml --profile domestic-stable up -d xhs-worker
    services=(xhs-worker)
    ;;
  kuaishou)
    docker compose -f compose.yaml -f compose.workers.yaml --profile domestic-stable up -d ks-worker
    services=(ks-worker)
    ;;
  douk-experimental)
    docker compose -f compose.yaml -f compose.workers.yaml --profile douk-experimental up -d douk-worker
    printf 'DouK 上游仍依赖交互式 Web API 模式。健康门未通过时，抖音会自动退回 gallery-dl/yt-dlp 与当前页保存。\n'
    services=(douk-worker)
    ;;
  *)
    printf '用法：bash scripts/start_workers.sh [stable|xhs|kuaishou|douk-experimental]\n' >&2
    exit 2
    ;;
esac
for service in "${services[@]}"; do
  healthy=false
  for _ in $(seq 1 30); do
    state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "social-archive-${service}-1" 2>/dev/null || true)"
    if [[ "$state" == "healthy" ]]; then healthy=true; break; fi
    sleep 2
  done
  if [[ "$healthy" != true ]]; then
    printf '%s 未通过健康门；系统已保持单平台降级，通用当前页保存与 CLI 兜底仍可用。\n' "$service" >&2
    [[ "$mode" == "douk-experimental" ]] || exit 1
  fi
done
printf '所选平台 Worker 已启动并完成可用性检查。\n'
