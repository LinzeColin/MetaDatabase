#!/usr/bin/env bash
# 在 VPS-3 上以 root 执行：部署/更新 Serenity 无人值守服务（幂等）。
# 代码：公开仓 MetaDatabase 的 Serenity-Alipay 稀疏检出到 /opt/serenity/src（root 所有，服务只读）。
set -euo pipefail
REPO_URL="${SERENITY_REPO_URL:-https://github.com/LinzeColin/MetaDatabase.git}"
REF="${SERENITY_REF:-main}"
SRC=/opt/serenity/src

mkdir -p /opt/serenity
if [ ! -d "$SRC/.git" ]; then
  git clone --depth 1 --filter=blob:none --sparse --branch "$REF" "$REPO_URL" "$SRC"
  git -C "$SRC" sparse-checkout set Serenity-Alipay
else
  git -C "$SRC" fetch --depth 1 origin "$REF"
  git -C "$SRC" reset --hard FETCH_HEAD
fi
chmod -R go-w "$SRC"
cp "$SRC/Serenity-Alipay/deploy/vps3/serenity-tick.service" /etc/systemd/system/
cp "$SRC/Serenity-Alipay/deploy/vps3/serenity-tick.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now serenity-tick.timer
systemctl list-timers serenity-tick.timer --no-pager
