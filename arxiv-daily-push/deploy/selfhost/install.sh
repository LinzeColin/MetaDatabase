#!/usr/bin/env bash
# 在服务器上以 root 运行：把本目录的脚本、unit、env 装到位。只动 ADP 自己的文件，
# 不碰 /usr/local/bin/linze-pull-deploy.sh、eei-pull-deploy.sh 与别的项目的 unit / env。
#
#   sudo bash arxiv-daily-push/deploy/selfhost/install.sh                 # 安装/更新；只启用「拉取式部署」定时器
#   sudo bash arxiv-daily-push/deploy/selfhost/install.sh --enable-jobs   # 数据迁完之后：启用每日任务与回填定时器
#   sudo bash arxiv-daily-push/deploy/selfhost/install.sh --check         # 只比对（服务器与仓库不一致则退出码 1）
#
# 为什么每日任务定时器默认不启用：先迁移数据、再开每日任务。空库上先跑一次每日任务，会让「当日已有运行记录」
# 挡住后面的迁移导入（迁移脚本拒绝覆盖非空库）。
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
MODE=${1:-install}
[ "$(id -u)" = 0 ] || { echo "需要 root" >&2; exit 77; }

declare -A DEST=(
  ["adp-pull-deploy.sh"]=/usr/local/bin/adp-pull-deploy.sh
  ["adp-daily-run.sh"]=/usr/local/bin/adp-daily-run.sh
  ["adp-record-failure.sh"]=/usr/local/bin/adp-record-failure.sh
  ["adp-import-d1.sh"]=/usr/local/bin/adp-import-d1.sh
  ["adp-web-pull.service"]=/etc/systemd/system/adp-web-pull.service
  ["adp-web-pull.timer"]=/etc/systemd/system/adp-web-pull.timer
  ["adp-daily.service"]=/etc/systemd/system/adp-daily.service
  ["adp-daily.timer"]=/etc/systemd/system/adp-daily.timer
  ["adp-backfill.service"]=/etc/systemd/system/adp-backfill.service
  ["adp-backfill.timer"]=/etc/systemd/system/adp-backfill.timer
  ["adp-failure@.service"]=/etc/systemd/system/adp-failure@.service
  ["adp.env"]=/etc/linze-pull-deploy/adp.env
  ["migrate_from_d1.py"]=/usr/local/share/adp/migrate_from_d1.py
)
SCHEMA_SRC="$HERE/../cloudflare/schema_cloud.sql"
SCHEMA_DEST=/usr/local/share/adp/schema_cloud.sql

if [ "$MODE" = "--check" ]; then
  rc=0
  for f in "${!DEST[@]}"; do
    if cmp -s "$HERE/$f" "${DEST[$f]}"; then echo "一致  ${DEST[$f]}"; else echo "不一致 ${DEST[$f]}"; rc=1; fi
  done
  if cmp -s "$SCHEMA_SRC" "$SCHEMA_DEST"; then echo "一致  $SCHEMA_DEST"; else echo "不一致 $SCHEMA_DEST"; rc=1; fi
  exit $rc
fi

if [ "$MODE" = "--enable-jobs" ]; then
  [ -f /etc/systemd/system/adp-daily.timer ] || { echo "先不带参数跑一遍 install.sh" >&2; exit 78; }
  systemctl enable --now adp-daily.timer adp-backfill.timer
  systemctl list-timers 'adp-*' --no-pager | sed -n '1,8p'
  exit 0
fi
[ "$MODE" = install ] || { echo "未知参数 $MODE" >&2; exit 64; }

for c in docker curl git flock python3 systemctl; do
  command -v "$c" >/dev/null || { echo "缺少命令：$c" >&2; exit 69; }
done
for f in adp-pull-deploy.sh adp-daily-run.sh adp-record-failure.sh adp-import-d1.sh; do bash -n "$HERE/$f"; done
[ -f "$SCHEMA_SRC" ] || { echo "找不到 $SCHEMA_SRC（sparse checkout 要包含整个 arxiv-daily-push/deploy）" >&2; exit 66; }

mkdir -p /etc/linze-pull-deploy /usr/local/share/adp
for f in "${!DEST[@]}"; do
  case "$f" in
    *.sh) mode=0755 ;;
    *) mode=0644 ;;
  esac
  install -m "$mode" "$HERE/$f" "${DEST[$f]}"
done
install -m 0644 "$SCHEMA_SRC" "$SCHEMA_DEST"

# 数据目录：唯一的持久状态。属主 = 容器内用户 10001（容器以非 root 运行，写不进 root 属主目录）
install -d -m 0750 -o 10001 -g 10001 /var/lib/adp /var/lib/adp/logs /var/lib/adp/backups

systemctl daemon-reload
systemctl enable --now adp-web-pull.timer
systemctl list-timers 'adp-*' --no-pager | sed -n '1,8p'
cat <<'EOF'

已安装。接下来（由运维/主线执行，详见 dev-notes/2026-09-30-ADP自托管.md）：
  1. 等第一次拉取式部署成功：  sudo /usr/local/bin/adp-pull-deploy.sh status adp
     （也可立即触发：          sudo systemctl start adp-web-pull.service）
  2. 导入 D1 导出：            sudo /usr/local/bin/adp-import-d1.sh /path/to/dump.sql --dry-run 后去掉 --dry-run
  3. 启用每日任务与回填：      sudo bash install.sh --enable-jobs
EOF
