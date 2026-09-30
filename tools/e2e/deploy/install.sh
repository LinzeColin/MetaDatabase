#!/usr/bin/env bash
# 在服务器上以 root 运行：把 linze-e2e、service、timer 装到位并启用 timer。
#   git clone --depth 1 --filter=blob:none --sparse https://github.com/LinzeColin/MetaDatabase.git /tmp/mdb-e2e \
#     && git -C /tmp/mdb-e2e sparse-checkout set tools/e2e && sudo bash /tmp/mdb-e2e/tools/e2e/deploy/install.sh
#   sudo bash install.sh --check     # 只比对服务器与仓库是否一致（不一致退出码 1）
# 脚本不会自我更新（避免「合入 main = 宿主机 root」）；改了本目录后在服务器上重跑 install.sh。
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
declare -A DEST=(
  [linze-e2e]=/usr/local/bin/linze-e2e
  [linze-e2e.service]=/etc/systemd/system/linze-e2e.service
  [linze-e2e.timer]=/etc/systemd/system/linze-e2e.timer
)
if [ "${1:-}" = "--check" ]; then
  rc=0
  for f in "${!DEST[@]}"; do
    if cmp -s "$HERE/$f" "${DEST[$f]}"; then echo "一致  ${DEST[$f]}"; else echo "不一致 ${DEST[$f]}"; rc=1; fi
  done
  exit $rc
fi
[ "$(id -u)" = 0 ] || { echo "需要 root" >&2; exit 77; }
bash -n "$HERE/linze-e2e"
install -m 0755 "$HERE/linze-e2e" "${DEST[linze-e2e]}"
install -m 0644 "$HERE/linze-e2e.service" "${DEST[linze-e2e.service]}"
install -m 0644 "$HERE/linze-e2e.timer" "${DEST[linze-e2e.timer]}"
systemd-analyze verify /etc/systemd/system/linze-e2e.service /etc/systemd/system/linze-e2e.timer || true
systemctl daemon-reload
systemctl enable --now linze-e2e.timer
systemctl list-timers linze-e2e.timer --no-pager | sed -n '1,3p'
