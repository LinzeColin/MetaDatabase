#!/usr/bin/env bash
# adp-record-failure.sh <失败的 unit 名> —— 由 adp-failure@.service（OnFailure）调用，把一次失败落成一行可查的记录。
#   /var/lib/adp/logs/failures.log          一行一次失败（最多保留 200 行）；网页 /api/selfhost/status 的 last_failure 读它
#   journalctl -t adp-failure               同一条进 journal（priority err）
# 容器里的 jobs.jsonl 另外记了每次尝试的细节；本脚本只负责「unit 整体失败了」这件事本身不被吞掉。
set -uo pipefail
UNIT=${1:-unknown}
[[ $UNIT =~ ^[A-Za-z0-9@._:-]+$ ]] || { echo "unit 名不合法" >&2; exit 64; }
DATA=${ADP_DATA_HOST_DIR:-/var/lib/adp}
LOG="$DATA/logs/failures.log"
mkdir -p "$DATA/logs"
code=$(systemctl show -p ExecMainStatus --value "$UNIT" 2>/dev/null || echo "?")
result=$(systemctl show -p Result --value "$UNIT" 2>/dev/null || echo "?")
case "$code" in
  1) why="运行失败" ;;
  2) why="arXiv 重试用尽仍没抓到" ;;
  3) why="抓取成功但库备份失败" ;;
  75) why="上一次还在跑" ;;
  78) why="缺配置或镜像" ;;
  *) why="见 journalctl -u $UNIT" ;;
esac
line="$(date -u +%FT%TZ) unit=$UNIT exit=$code result=$result $why"
echo "$line" >> "$LOG"
tail -n 200 "$LOG" > "$LOG.tmp" && mv -f "$LOG.tmp" "$LOG"
chown 10001:10001 "$DATA/logs" "$LOG" 2>/dev/null; chmod 0644 "$LOG" 2>/dev/null
logger -p user.err -t adp-failure -- "$line"
echo "$line" >&2
exit 0
