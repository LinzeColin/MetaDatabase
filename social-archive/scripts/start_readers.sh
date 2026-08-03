#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)";cd "$ROOT"
profile="${1:-readers}"
case "$profile" in
  readers) required_secrets=(karakeep.env linkwarden.env) ;;
  karakeep) required_secrets=(karakeep.env) ;;
  linkwarden) required_secrets=(linkwarden.env) ;;
  archivebox) required_secrets=() ;;
  *) echo '只允许 readers、karakeep、linkwarden 或 archivebox' >&2;exit 2 ;;
esac
for secret in "${required_secrets[@]:-}"; do
  [[ -n "$secret" ]] || continue
  [[ -s "runtime/secrets/$secret" ]] || { echo "缺少 runtime/secrets/${secret}；请先运行 bash scripts/install.sh" >&2; exit 2; }
done
docker network inspect social-archive-readers >/dev/null 2>&1 || docker network create social-archive-readers >/dev/null
docker compose -f compose.readers.yaml --profile "$profile" up -d
printf '可选阅读器已启动。Karakeep：http://127.0.0.1:3000；Linkwarden：http://127.0.0.1:3001；ArchiveBox：http://127.0.0.1:8000\n'
