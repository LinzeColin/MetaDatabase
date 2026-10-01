#!/usr/bin/env bash
# 在服务器上以 root 运行：把本目录的脚本、unit、env 装到位并启用 timer。只动 eei-api 自己的文件，
# 不碰宇宙（eei-universe）与别的项目的脚本 / unit / env，也不动 eei-db。
#   sudo bash EEI/apps/api/deploy/install.sh            # 安装/更新并启用
#   sudo bash EEI/apps/api/deploy/install.sh --check    # 只比对（服务器与仓库不一致则退出码 1）
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
MODE=${1:-install}
[ "$(id -u)" = 0 ] || { echo "需要 root" >&2; exit 77; }

declare -A DEST=(
  ["eei-api-pull-deploy.sh"]=/usr/local/bin/eei-api-pull-deploy.sh
  ["eei-api-pull.service"]=/etc/systemd/system/eei-api-pull.service
  ["eei-api-pull.timer"]=/etc/systemd/system/eei-api-pull.timer
  ["eei-api.env"]=/etc/linze-pull-deploy/eei-api.env
)
SECRET=/etc/eei-api/eei-api.secret.env
if [ "$MODE" = "--check" ]; then
  rc=0
  for f in "${!DEST[@]}"; do
    if cmp -s "$HERE/$f" "${DEST[$f]}"; then echo "一致  ${DEST[$f]}"; else echo "不一致 ${DEST[$f]}"; rc=1; fi
  done
  if [ -r "$SECRET" ]; then echo "有    $SECRET"; else echo "缺    $SECRET（DATABASE_URL，见 README）"; rc=1; fi
  exit $rc
fi
[ "$MODE" = install ] || { echo "未知参数 $MODE" >&2; exit 64; }
bash -n "$HERE/eei-api-pull-deploy.sh"
mkdir -p /etc/linze-pull-deploy /etc/eei-api
install -m 0755 "$HERE/eei-api-pull-deploy.sh" "${DEST[eei-api-pull-deploy.sh]}"
install -m 0644 "$HERE/eei-api-pull.service" "${DEST[eei-api-pull.service]}"
install -m 0644 "$HERE/eei-api-pull.timer" "${DEST[eei-api-pull.timer]}"
install -m 0644 "$HERE/eei-api.env" "${DEST[eei-api.env]}"
if [ ! -r "$SECRET" ]; then
  echo "提示：还没有 $SECRET（600，内容 DATABASE_URL=postgresql://eei_reader:<密码>@eei-db:5432/eei）；没有它首次部署会失败并退避。" >&2
fi
systemctl daemon-reload
systemctl enable --now eei-api-pull.timer
systemctl list-timers eei-api-pull.timer --no-pager | sed -n '1,3p'
