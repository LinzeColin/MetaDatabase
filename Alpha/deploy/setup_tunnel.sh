#!/usr/bin/env bash
# Cloudflare 快速隧道:把仅回环的控制页(127.0.0.1:8443)安全暴露成公网 https。
#   sudo bash deploy/setup_tunnel.sh
# 特性:
# - 官方 cloudflared 单二进制(Cloudflare GitHub Releases,amd64);
# - 快速隧道无需 Cloudflare 账号;地址为随机 *.trycloudflare.com,重启会更换;
# - alpha-tunnel.service 常驻 + alpha-tunnel-url.service 在隧道就绪后解析新地址,
#   经发件箱邮件通知 owner(地址一变自动再通知);
# - 页面本身仍有 64 位令牌门:公网可达 ≠ 可看,无令牌一律 401。
set -euo pipefail
[ "$(id -u)" = "0" ] || { echo "请用 sudo 运行"; exit 1; }

BIN=/usr/local/bin/cloudflared
if [ ! -x "$BIN" ]; then
  echo ">> 下载官方 cloudflared(amd64)"
  curl -sfL --retry 3 -o "$BIN" \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod 755 "$BIN"
fi
"$BIN" --version

cat > /etc/systemd/system/alpha-tunnel.service <<'UNIT'
[Unit]
Description=Alpha 控制页 Cloudflare 快速隧道(只读仪表盘;页面自带令牌门)
After=network-online.target alpha-control-page.service
Wants=network-online.target

[Service]
ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8443
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

cat > /usr/local/bin/alpha-tunnel-url.sh <<'HOOK'
#!/usr/bin/env bash
# 解析当前隧道地址;与上次不同则经发件箱邮件通知 owner。
set -u
LAST=/opt/alpha/runtime/tunnel_url.txt
for i in $(seq 1 30); do
  URL=$(journalctl -u alpha-tunnel --no-pager -n 200 2>/dev/null \
        | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1)
  [ -n "$URL" ] && break
  sleep 4
done
[ -n "${URL:-}" ] || { echo "未解析到隧道地址"; exit 1; }
PREV=$(cat "$LAST" 2>/dev/null || true)
echo "$URL" > "$LAST"; chown alpha:alpha "$LAST" 2>/dev/null || true
echo "隧道地址: $URL"
if [ "$URL" != "$PREV" ]; then
  sudo -u alpha bash -c "set -a; . /opt/alpha/env; set +a; cd /opt/alpha/MetaDatabase/Alpha && HOME=/opt/alpha /opt/alpha/venv/bin/python - <<PY
from backend.app.workers.main_common import build_runtime
rt = build_runtime()
rt['outbox'].enqueue(event_type='DASHBOARD_URL_CHANGED', payload={
    'msg': '模拟盘仪表盘地址(重启后会更换,以最新邮件为准);打开后按提示输入你的控制令牌',
    'url': '$URL'})
print('地址通知已入队')
PY"
fi
HOOK
chmod 755 /usr/local/bin/alpha-tunnel-url.sh

cat > /etc/systemd/system/alpha-tunnel-url.service <<'UNIT'
[Unit]
Description=Alpha 隧道地址解析与通知(地址变化即邮件 owner)
After=alpha-tunnel.service
Requires=alpha-tunnel.service

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 8
ExecStart=/usr/local/bin/alpha-tunnel-url.sh
UNIT

# 隧道每次(重)启动都触发一次地址解析
mkdir -p /etc/systemd/system/alpha-tunnel.service.d
cat > /etc/systemd/system/alpha-tunnel.service.d/notify.conf <<'UNIT'
[Unit]
Wants=alpha-tunnel-url.service
UNIT

systemctl daemon-reload
systemctl enable --now alpha-tunnel >/dev/null 2>&1
systemctl restart alpha-tunnel
systemctl start alpha-tunnel-url || true
sleep 2
echo "=== 隧道状态 ==="
systemctl is-active alpha-tunnel
cat /opt/alpha/runtime/tunnel_url.txt 2>/dev/null || /usr/local/bin/alpha-tunnel-url.sh
