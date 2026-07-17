#!/usr/bin/env bash
# Alpha 云主机加固与安装(DEPLOY_RUNBOOK_ORACLE 第 2-3 节;Ubuntu 22.04)
# 用法: sudo bash deploy/setup.sh   (owner 部署日,与 15 分钟凭据动作配合)
set -euo pipefail

echo ">> 1/6 系统加固"
apt-get update -y
apt-get install -y ufw unattended-upgrades fail2ban chrony python3.11 python3.11-venv postgresql git
timedatectl set-timezone UTC
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 443/tcp
ufw --force enable
systemctl enable --now fail2ban chrony

echo ">> 2/6 服务用户与目录"
id -u alpha &>/dev/null || useradd --system --create-home --home-dir /opt/alpha alpha
install -d -m 750 -o alpha -g alpha /opt/alpha
install -d -m 700 -o alpha -g alpha /opt/alpha/runtime

echo ">> 3/6 PostgreSQL(仅回环)"
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='alpha'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE ROLE alpha LOGIN PASSWORD 'CHANGE_ME_ON_DEPLOY_DAY'"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='alpha'" | grep -q 1 || \
  sudo -u postgres createdb -O alpha alpha

echo ">> 4/6 应用"
if [ ! -d /opt/alpha/MetaDatabase ]; then
  sudo -u alpha git clone --filter=blob:none --sparse https://github.com/LinzeColin/MetaDatabase.git /opt/alpha/MetaDatabase
  sudo -u alpha git -C /opt/alpha/MetaDatabase sparse-checkout set Alpha
fi
sudo -u alpha python3.11 -m venv /opt/alpha/venv
sudo -u alpha /opt/alpha/venv/bin/pip install -e "/opt/alpha/MetaDatabase/Alpha[dev]"

echo ">> 5/6 环境文件(owner 部署日填值)"
if [ ! -f /opt/alpha/env ]; then
  install -m 600 -o alpha -g alpha /opt/alpha/MetaDatabase/Alpha/deploy/env.template /opt/alpha/env
  echo "!! 请 owner 填写 /opt/alpha/env 中全部 <REQUIRED> 值(权限已 600)"
fi

echo ">> 6/6 systemd 单元"
cp /opt/alpha/MetaDatabase/Alpha/deploy/systemd/alpha-*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable alpha-opend alpha-trading-worker alpha-notify-worker alpha-supervisor alpha-control-page

echo ""
echo ">> 完成。owner 15 分钟动作:填 /opt/alpha/env -> systemctl start alpha-opend(首登验证码)"
echo ">> 然后: systemctl start alpha-trading-worker alpha-notify-worker alpha-supervisor alpha-control-page"
echo ">> 验收三连:python3 scripts/probe_real_machine.py -> 收到测试邮件 -> 手机开控制页停机/恢复一次"
