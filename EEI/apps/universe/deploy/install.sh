#!/usr/bin/env bash
# 在服务器上以 root 运行：把本目录的脚本、unit、env 装到位并启用 timer。只动 EEI 商域宇宙自己的文件，
# 不碰 /usr/local/bin/linze-pull-deploy.sh 与别的项目的 unit / env。
#   sudo bash EEI/apps/universe/deploy/install.sh            # 安装/更新并启用
#   sudo bash EEI/apps/universe/deploy/install.sh --check    # 只比对（服务器与仓库不一致则退出码 1）
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
MODE=${1:-install}
[ "$(id -u)" = 0 ] || { echo "需要 root" >&2; exit 77; }

declare -A DEST=(
  ["eei-pull-deploy.sh"]=/usr/local/bin/eei-pull-deploy.sh
  ["eei-universe-pull.service"]=/etc/systemd/system/eei-universe-pull.service
  ["eei-universe-pull.timer"]=/etc/systemd/system/eei-universe-pull.timer
  ["eei-universe.env"]=/etc/linze-pull-deploy/eei-universe.env
)
if [ "$MODE" = "--check" ]; then
  rc=0
  for f in "${!DEST[@]}"; do
    if cmp -s "$HERE/$f" "${DEST[$f]}"; then echo "一致  ${DEST[$f]}"; else echo "不一致 ${DEST[$f]}"; rc=1; fi
  done
  exit $rc
fi
[ "$MODE" = install ] || { echo "未知参数 $MODE" >&2; exit 64; }
bash -n "$HERE/eei-pull-deploy.sh"
mkdir -p /etc/linze-pull-deploy
install -m 0755 "$HERE/eei-pull-deploy.sh" "${DEST[eei-pull-deploy.sh]}"
install -m 0644 "$HERE/eei-universe-pull.service" "${DEST[eei-universe-pull.service]}"
install -m 0644 "$HERE/eei-universe-pull.timer" "${DEST[eei-universe-pull.timer]}"
install -m 0644 "$HERE/eei-universe.env" "${DEST[eei-universe.env]}"
systemctl daemon-reload
systemctl enable --now eei-universe-pull.timer
systemctl list-timers eei-universe-pull.timer --no-pager | sed -n '1,3p'
