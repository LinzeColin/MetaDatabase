#!/usr/bin/env bash
# 复核「保命的那几个 unit 到底启用了没有」。**在宿主机上跑。**
#
# 为什么需要它：prepare_systemd_host.sh 按设计**不启用**任何 unit
# （装好 → Owner 验收 → 显式启用），这个取舍本身是对的。
# 但交接只说了一句「由 Owner 显式启用」，没说要启用哪几个，
# 也没有任何东西回头核一遍。
#
# 生产实测（2026-08-04）后果：
#   social-archive.service          enabled / active     ✓
#   social-archive-status.timer     enabled / active     ✓
#   social-archive-backup.timer     **disabled**         ✗ 从来没跑过
#   social-archive-replication.timer **disabled**        ✗ 从来没跑过
#   social-archive-private-database-sync.timer **disabled** ✗ 从来没跑过
#
#   → 549 个制品里 **530 个一个异地副本都没有**
#   → journalctl 90 天内三个 unit 全是 "No entries"
#
# 数据只存在一块盘上，而产品的卖点是「归档」。
set -uo pipefail

REQUIRED=(
  social-archive.service
  social-archive-backup.timer
  social-archive-replication.timer
  social-archive-private-database-sync.timer
  social-archive-status.timer
  social-archive-cloudflared.service
)

BAD=0
printf '%-46s %-10s %s\n' UNIT 启用 运行
printf '%.0s-' {1..70}; printf '\n'
for unit in "${REQUIRED[@]}"; do
  enabled="$(systemctl is-enabled "${unit}" 2>&1 || true)"
  active="$(systemctl is-active "${unit}" 2>&1 || true)"
  printf '%-46s %-10s %s\n' "${unit}" "${enabled}" "${active}"
  case "${enabled}" in
    enabled|enabled-runtime|static|indirect) ;;
    *) BAD=1 ;;
  esac
done

if [ "${BAD}" = "1" ]; then
  printf '\n✗ 有 unit 没有启用。**这不是「少个功能」**：\n'
  printf '  备份没启用 = 没有任何定时备份\n'
  printf '  复制没启用 = 制品只存在于本机这一块盘上\n'
  printf '  两者都静默 —— 界面照样显示「已归档」。\n'
  printf '\n启用命令（由 Owner 执行，本脚本只读不改）：\n'
  for unit in "${REQUIRED[@]}"; do
    printf '  systemctl enable --now %s\n' "${unit}"
  done
  printf '\n启用后重跑本脚本复核；再看 /v1/status 的 storage.completion。\n'
  exit 1
fi
printf '\n✓ 保命的 unit 都已启用。\n'
