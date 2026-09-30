#!/usr/bin/env bash
# 在服务器上以 root 运行：把 deploy/vps 里的脚本、unit、配置装到位，起 nginx 容器，启用两个 timer。
#   sudo bash install.sh            # 安装/更新并启用（幂等）
#   sudo bash install.sh --check    # 只比对服务器与仓库是否一致（不一致退出码 1）
#   sudo bash install.sh --seed     # 安装之外，首次迁移时用：从公开仓 gh-pages 的 fifa/ 取旧站点当起点（账本、回测缓存、存档接着用）
# 不自我更新：脚本和 unit 只由本脚本安装，避免「合入 main = 拿到宿主机 root」。
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
MODE=${1:-install}
[ "$(id -u)" = 0 ] || { echo "需要 root" >&2; exit 77; }

declare -A DEST=(
  ["fifa-daily-pull.sh"]=/usr/local/bin/fifa-daily-pull.sh
  ["fifa-daily-run.sh"]=/usr/local/bin/fifa-daily-run.sh
  ["fifa-daily-notify.sh"]=/usr/local/bin/fifa-daily-notify.sh
  ["fifa-daily.service"]=/etc/systemd/system/fifa-daily.service
  ["fifa-daily.timer"]=/etc/systemd/system/fifa-daily.timer
  ["fifa-daily-pull.service"]=/etc/systemd/system/fifa-daily-pull.service
  ["fifa-daily-pull.timer"]=/etc/systemd/system/fifa-daily-pull.timer
  ["fifa-daily-failed@.service"]=/etc/systemd/system/fifa-daily-failed@.service
  ["fifa-daily.env"]=/etc/fifa-daily/fifa-daily.env
  ["nginx.conf"]=/etc/fifa-daily/nginx.conf
  ["docker-compose.yml"]=/etc/fifa-daily/docker-compose.yml
)
if [ "$MODE" = "--check" ]; then
  rc=0
  for f in "${!DEST[@]}"; do
    if cmp -s "$HERE/$f" "${DEST[$f]}"; then echo "一致  ${DEST[$f]}"; else echo "不一致 ${DEST[$f]}"; rc=1; fi
  done
  exit $rc
fi
case "$MODE" in install|--seed) ;; *) echo "未知参数 $MODE" >&2; exit 64 ;; esac
for s in fifa-daily-pull.sh fifa-daily-run.sh fifa-daily-notify.sh; do bash -n "$HERE/$s"; done

id fifa-daily >/dev/null 2>&1 || useradd --system --home-dir /opt/fifa-daily --shell /usr/sbin/nologin fifa-daily
install -d -o fifa-daily -g fifa-daily -m 0755 /opt/fifa-daily /var/lib/fifa-daily
install -d -m 0755 /etc/fifa-daily
for f in "${!DEST[@]}"; do
  case "$f" in *.sh) m=0755 ;; *) m=0644 ;; esac
  install -m "$m" "$HERE/$f" "${DEST[$f]}"
done
# Gatus 心跳令牌：首次生成随机值（root:fifa-daily 0640）；已有则保留。令牌需要同时写进 Gatus 配置的 external-endpoints
if [ ! -s /etc/fifa-daily/gatus.token ]; then
  ( umask 077; head -c 24 /dev/urandom | base64 | tr -d '/+=\n' > /etc/fifa-daily/gatus.token )
  echo "已生成 /etc/fifa-daily/gatus.token（把它写进 Gatus 配置 external-endpoints 的 token）"
fi
chown root:fifa-daily /etc/fifa-daily/gatus.token; chmod 0640 /etc/fifa-daily/gatus.token
systemctl daemon-reload

if [ "$MODE" = "--seed" ] && [ ! -e /var/lib/fifa-daily/current ]; then
  tmp=$(mktemp -d /var/lib/fifa-daily/.seed.XXXXXX); chown fifa-daily:fifa-daily "$tmp"
  runuser -u fifa-daily -- git clone -q --depth 1 --branch gh-pages https://github.com/LinzeColin/MetaDatabase.git "$tmp/pages"
  if [ -f "$tmp/pages/fifa/data/ledger.json" ]; then
    id="seed-$(date -u +%Y%m%dT%H%M%SZ)"
    runuser -u fifa-daily -- mkdir -p "/var/lib/fifa-daily/releases/$id"
    runuser -u fifa-daily -- cp -a "$tmp/pages/fifa/." "/var/lib/fifa-daily/releases/$id/"
    runuser -u fifa-daily -- ln -sfn "releases/$id" /var/lib/fifa-daily/current
    echo "已从 gh-pages 取得旧站点作为起点：releases/$id"
  else
    echo "gh-pages 上没有旧账本（已迁走？），从空状态开始"
  fi
  rm -rf "$tmp"
fi

docker compose -f /etc/fifa-daily/docker-compose.yml up -d
systemctl enable --now fifa-daily-pull.timer fifa-daily.timer
systemctl list-timers 'fifa-daily*' --no-pager | sed -n '1,4p'
