#!/usr/bin/env bash
# 在主机上拉起真实 72h 烤机（脱离 SSH 会话,systemd 瞬态单元,断线不影响）。
#   ssh ubuntu@HOST 'sudo bash -s' < deploy/start_soak_host.sh
# 自足:run_soak.py --hours 72 用内置 sqlite + 假适配器 + 内存邮件汇,不依赖任何凭据。
# 幂等:已在跑则报告不重复起。日志入 journald(unit=alpha-soak72)。
set -euo pipefail
APP=/opt/alpha
SRC="$APP/MetaDatabase/Alpha"
UNIT=alpha-soak72

if systemctl is-active --quiet "$UNIT"; then
  echo "SOAK_ALREADY_RUNNING unit=$UNIT"
  systemctl show "$UNIT" -p ActiveEnterTimestamp --value
  exit 0
fi
# 清掉上一轮已退出的同名单元（若有）
systemctl reset-failed "$UNIT" 2>/dev/null || true

# 拉起:以 alpha 用户、在源码目录、跑满 72 真实小时,产物落 reports/soak/soak_host.json
systemd-run --unit="$UNIT" --uid=alpha --gid=alpha \
  --working-directory="$SRC" \
  --property=Restart=no \
  "$APP/venv/bin/python" scripts/run_soak.py --hours 72 --out reports/soak

sleep 2
echo "SOAK_STARTED unit=$UNIT started_at=$(date -u +%FT%TZ)"
systemctl status "$UNIT" --no-pager -l | head -8 || true
echo ">> 完工时间约 72h 后;期间 journalctl -u $UNIT 可看进度,产物 $SRC/reports/soak/soak_host.json"
