#!/usr/bin/env bash
# 看门狗：按**服务实际能不能应答**判断死活，不看 systemd 怎么说。
#
# 为什么不能信 systemd：2026-07-30 抓到过一次 `active (running)` 而
# `Main PID` 指向的进程**已经不存在**——ExecStart 是
# `flock -n <lock> run-cyberboss.sh`，systemd 跟的是 flock 那个壳，壳没了
# 子进程还活着，于是 Restart=always 一次都不会触发。反过来也一样：壳活着
# 而里面的 node 死了，systemd 照样报 active。
#
# 所以这里只问两个能直接回答"用户现在用不用得了"的问题：
#   1. 本机 healthz 通不通（应用真的在应答吗）
#   2. 公网入口通不通（隧道真的在转发吗）
# 任何一个连续失败到阈值就重启对应的 unit。判据是行为，不是状态字段。
#
# 这个脚本跑在服务器上，由 systemd timer 拉起。主人的电脑关机也照样工作——
# 之前那三次公网中断都是靠人从一台 Mac 上手工 systemctl start 恢复的。
set -uo pipefail

SERVICE="cyberboss-cloud.service"
TUNNEL="cyberboss-cf-tunnel.service"
# 端口**从配置里读**，不写死。
#
# 第一版把默认值写成 8787（部署脚本里的默认），而这台机器上实际是 8789——
# 看门狗于是每一轮都判"应用不通"，再过 6 分钟就会去重启一个完全健康的服务。
# 一个判错的看门狗比没有看门狗危险：它会把偶发变成周期性宕机。
# 所以：读到就用，读不到宁可**放弃本机这一项检查**，也不要拿一个猜的端口去判死。
PORT="$(grep -hoP '^CB_PORTAL_PORT=\K[0-9]+' /etc/cyberboss/*.env 2>/dev/null | tail -1)"
HEALTH_URL=""
[ -n "$PORT" ] && HEALTH_URL="http://127.0.0.1:${PORT}/healthz"
PUBLIC_URL="${CB_PUBLIC_ORIGIN:-https://boss.linzezhang.com}/healthz"
STATE_DIR=/run/cyberboss-watchdog
# 连续失败几次才动手。1 次就重启会把"正在启动"误判成"死了"，
# 而这个服务启动本来就慢（notify 那一跳能拖到几十秒）。
THRESHOLD=3

mkdir -p "$STATE_DIR"

probe() { # url -> 0 通 / 1 不通
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$1" 2>/dev/null)"
  [ "$code" = "200" ]
}

# 连续失败计数。达到阈值就重启并清零，避免每一轮都重启。
bump() { # name -> 回显当前连续失败次数
  local f="$STATE_DIR/$1.fail" n=0
  [ -f "$f" ] && n="$(cat "$f" 2>/dev/null || echo 0)"
  n=$((n + 1))
  echo "$n" >"$f"
  echo "$n"
}
clear_fail() { rm -f "$STATE_DIR/$1.fail"; }

# ── 应用 ────────────────────────────────────────────────
# 读不到端口就跳过这一项：不知道 ≠ 坏了。下面公网那一项仍然会兜住整体可用性。
if [ -z "$HEALTH_URL" ]; then
  echo "[watchdog] 读不到 CB_PORTAL_PORT，跳过本机检查（不当作故障）"
  clear_fail app
elif probe "$HEALTH_URL"; then
  clear_fail app
else
  n="$(bump app)"
  echo "[watchdog] 本机 healthz 不通（连续 $n 次）$HEALTH_URL"
  if [ "$n" -ge "$THRESHOLD" ]; then
    echo "[watchdog] 重启 $SERVICE"
    systemctl restart "$SERVICE" || true
    clear_fail app
  fi
fi

# ── 该开着却没开的 unit ─────────────────────────────────
# 这一条不设阈值：unit 是 enabled 却不是 active，是个**确定的**错误状态，
# 不是一次可能抖动的探测。
#
# 为什么单靠探测不够：停掉隧道之后公网还会 200 一小会儿——Cloudflare 边缘手里
# 还攥着旧连接。看门狗那时看到 200 就什么都不做，等边缘超时才变 530，于是又是
# 一次"没人知道的静默中断"。状态判据补上这个空窗。
for unit in "$SERVICE" "$TUNNEL"; do
  systemctl is-enabled --quiet "$unit" 2>/dev/null || continue
  state="$(systemctl is-active "$unit" 2>/dev/null)"
  # 只在**确定停着**的时候动手。
  #
  # activating / deactivating 是正在换版本的中间态：这个服务启动本来就慢（notify
  # 那一跳能拖几分钟）。原来写的是"不是 active 就拉起来"，于是部署重启到一半时
  # 看门狗会再踹一脚，两个 start 叠在一起——今天版本反复横跳、同时跑着两个部署，
  # 这是其中一个推手。看门狗不该和部署打架。
  case "$state" in
    inactive|failed) ;;
    *) continue ;;
  esac
  echo "[watchdog] $unit 该开着却没开（state=$state），拉起来"
  systemctl start "$unit" || true
done

# ── 公网入口 ────────────────────────────────────────────
# 单独判：应用好好的、隧道死了，是这台机器上最常见的故障形态，
# 而且从服务器内部完全看不出来——本机 8787 一直是 200。
if probe "$PUBLIC_URL"; then
  clear_fail tunnel
else
  n="$(bump tunnel)"
  echo "[watchdog] 公网入口不通（连续 $n 次）"
  if [ "$n" -ge "$THRESHOLD" ]; then
    echo "[watchdog] 重启 $TUNNEL"
    systemctl restart "$TUNNEL" || true
    clear_fail tunnel
  fi
fi

exit 0
