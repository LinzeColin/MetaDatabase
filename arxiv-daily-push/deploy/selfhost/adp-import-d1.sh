#!/usr/bin/env bash
# adp-import-d1.sh <dump.sql | --json-dir DIR | --json FILE> [--force] [--dry-run]
# 一次性：把 D1 adp-mirror 的导出导入 /var/lib/adp/adp.sqlite（实际工作由 migrate_from_d1.py 完成，
# 它随仓库在 /usr/local/share/adp/ 下；本脚本只负责：在正确位置跑、导入后把属主还给容器用户 10001、打印新鲜度）。
# 先 --dry-run 演练一遍再正式导入。重复导入会被拒绝（目标库已有数据），除非明确 --force。
set -euo pipefail
DATA=${ADP_DATA_HOST_DIR:-/var/lib/adp}
PY=${ADP_MIGRATE_PY:-/usr/local/share/adp/migrate_from_d1.py}
SCHEMA=${ADP_SCHEMA_SQL:-/usr/local/share/adp/schema_cloud.sql}
[ "$(id -u)" = 0 ] || { echo "需要 root（要把属主还给容器用户）" >&2; exit 77; }
[ -f "$PY" ] || { echo "找不到 $PY（先跑 install.sh）" >&2; exit 78; }
[ $# -ge 1 ] || { echo "用法: $0 <dump.sql> [--force] [--dry-run]  |  $0 --json-dir DIR | --json FILE" >&2; exit 64; }
args=("$@")
case "${1:-}" in --json-dir|--json|--sql) ;; *) args=(--sql "$1" "${@:2}") ;; esac
python3 "$PY" --db "$DATA/adp.sqlite" --schema "$SCHEMA" "${args[@]}"
chown -R 10001:10001 "$DATA"
echo "--- 导入后：" >&2
live=$(docker ps -q --filter "label=linze.pull.app=adp" --filter status=running | head -n1)
if [ -n "$live" ]; then
  docker exec "$live" wget -qO- "http://127.0.0.1:8080/api/selfhost/status" >&2 || echo "（取不到状态，见 journalctl / docker logs）" >&2
else
  echo "（还没有线上容器：先等拉取式部署成功，再看 https://<域名>/api/selfhost/status）" >&2
fi
