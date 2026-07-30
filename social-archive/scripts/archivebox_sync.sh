#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
QUEUE="${1:-runtime/exports/readers/archivebox-urls.txt}"
[[ -s "$QUEUE" ]] || { echo 'ArchiveBox 队列为空，无需同步。'; exit 0; }
case "${SOCIAL_ARCHIVE_L2_ENABLED:-false}" in
  1|true|TRUE|yes|YES|on|ON) ;;
  *) echo 'L2 默认关闭；显式设置 SOCIAL_ARCHIVE_L2_ENABLED=true 后才会提交 ArchiveBox 队列。' >&2; exit 3 ;;
esac
docker network inspect social-archive-readers >/dev/null 2>&1 || docker network create social-archive-readers >/dev/null
docker compose -f compose.readers.yaml --profile archivebox up -d archivebox
docker compose -f compose.readers.yaml exec -T archivebox archivebox add --parser=urls --depth=0 < "$QUEUE"
printf 'ArchiveBox URL 队列已提交：%s
' "$QUEUE"
