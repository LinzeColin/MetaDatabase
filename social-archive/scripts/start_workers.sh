#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mode="${1:-stable}"
mkdir -p runtime/vendor-output/xhs runtime/vendor-output/kuaishou runtime/vendor-output/douk
case "$mode" in
  stable)
    python3 scripts/vendor_sync.py --source xhs_downloader --source ks_downloader --resolve-and-lock
    profile=domestic-stable; services=(xhs-worker ks-worker)
    ;;
  xhs)
    python3 scripts/vendor_sync.py --source xhs_downloader --resolve-and-lock
    profile=xhs; services=(xhs-worker)
    ;;
  kuaishou)
    python3 scripts/vendor_sync.py --source ks_downloader --resolve-and-lock
    profile=kuaishou; services=(ks-worker)
    ;;
  douk-experimental)
    python3 scripts/vendor_sync.py --source douk --resolve-and-lock
    profile=douk-experimental; services=(douk-worker)
    printf 'DouK 为实验路径。健康门失败时，抖音自动退回当前页保存、gallery-dl 或 yt-dlp。\n'
    ;;
  *)
    printf '用法：bash scripts/start_workers.sh [stable|xhs|kuaishou|douk-experimental]\n' >&2
    exit 2
    ;;
esac

docker compose -f compose.yaml -f compose.workers.yaml --profile "$profile" up -d "${services[@]}"
for service in "${services[@]}"; do
  healthy=false
  for _ in $(seq 1 36); do
    container_id="$(docker compose -f compose.yaml -f compose.workers.yaml --profile "$profile" ps -q "$service")"
    state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
    if [[ "$state" == "healthy" ]]; then healthy=true; break; fi
    if [[ "$state" == "exited" || "$state" == "dead" ]]; then break; fi
    sleep 2
  done
  if [[ "$healthy" != true ]]; then
    printf '%s 未通过健康门；该平台保持降级，其他平台与普通网页保存继续可用。\n' "$service" >&2
    [[ "$mode" == "douk-experimental" ]] || exit 1
  fi
done
printf '所选平台 Worker 已启动并通过可用性检查。\n'
