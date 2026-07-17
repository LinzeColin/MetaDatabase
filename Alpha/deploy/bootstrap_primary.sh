#!/usr/bin/env bash
# Alpha 主部署节点从零 bootstrap（裸 Ubuntu 24.04 amd64，如 OVH VPS）。
# 与 Oracle cloud-init 等价，但适配「已存在的裸机 + 纯 SSH key」路径:
#   ssh ubuntu@HOST 'sudo bash -s' < deploy/bootstrap_primary.sh
# 幂等:重复运行安全。版本容错:自动选 python3.12/3.11。
# 红线:不写任何秘密到仓库/日志;LIVE_TRADING_ENABLED=0;券商/邮件保持 <REQUIRED> 待 owner。
set -euo pipefail
REPO_URL="https://github.com/LinzeColin/MetaDatabase.git"
APP=/opt/alpha
SRC="$APP/MetaDatabase/Alpha"
LOG="$APP/deploy_boot.log"

echo ">> 0/7 选 Python 版本"
PY=""
for c in python3.12 python3.11 python3; do command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -n "$PY" ] || { echo "FAIL: 无 python3"; exit 1; }
echo "   使用 $PY ($("$PY" --version 2>&1))"

echo ">> 1/7 系统加固（不动 22 端口，绝不自锁）"
export DEBIAN_FRONTEND=noninteractive
APT="apt-get -o DPkg::Lock::Timeout=600 -y"   # 等锁最多 10 分钟,避让开机 unattended-upgrades
$APT update
$APT install git ufw fail2ban unattended-upgrades chrony postgresql \
  "${PY}-venv" "${PY}-dev" build-essential curl >/dev/null
timedatectl set-timezone UTC || true
ufw allow 22/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
yes | ufw enable >/dev/null 2>&1 || ufw --force enable
systemctl enable --now fail2ban chrony >/dev/null 2>&1 || true

echo ">> 2/7 服务用户与目录"
id -u alpha &>/dev/null || useradd --system --create-home --home-dir "$APP" alpha
install -d -m 750 -o alpha -g alpha "$APP"
install -d -m 700 -o alpha -g alpha "$APP/runtime"

echo ">> 3/7 PostgreSQL（仅回环，随机密码）"
systemctl enable --now postgresql >/dev/null 2>&1 || true
DBPASS_FILE="$APP/.dbpass"
if [ ! -f "$DBPASS_FILE" ]; then
  head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32 > "$DBPASS_FILE"
  chmod 600 "$DBPASS_FILE"; chown alpha:alpha "$DBPASS_FILE"
fi
DBPASS="$(cat "$DBPASS_FILE")"
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='alpha'" | grep -q 1 \
  && sudo -u postgres psql -c "ALTER ROLE alpha LOGIN PASSWORD '$DBPASS'" >/dev/null \
  || sudo -u postgres psql -c "CREATE ROLE alpha LOGIN PASSWORD '$DBPASS'" >/dev/null
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='alpha'" | grep -q 1 \
  || sudo -u postgres createdb -O alpha alpha

echo ">> 4/7 拉取应用（公开仓，稀疏只取 Alpha）"
if [ ! -d "$APP/MetaDatabase/.git" ]; then
  sudo -u alpha git clone --filter=blob:none --sparse "$REPO_URL" "$APP/MetaDatabase"
  sudo -u alpha git -C "$APP/MetaDatabase" sparse-checkout set Alpha
else
  sudo -u alpha git -C "$APP/MetaDatabase" fetch --quiet origin main
  sudo -u alpha git -C "$APP/MetaDatabase" reset --hard origin/main --quiet
fi

echo ">> 5/7 venv 与依赖"
[ -x "$APP/venv/bin/python" ] || sudo -u alpha "$PY" -m venv "$APP/venv"
sudo -u alpha "$APP/venv/bin/pip" install --quiet --upgrade pip
sudo -u alpha "$APP/venv/bin/pip" install --quiet -e "$SRC[dev]"

echo ">> 6/7 环境文件（生成非敏感值；券商/邮件保持 <REQUIRED>）"
if [ ! -f "$APP/env" ]; then
  install -m 600 -o alpha -g alpha "$SRC/deploy/env.template" "$APP/env"
  CTOK="$(head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 64)"
  sudo -u alpha sed -i \
    -e "s#postgresql+psycopg://alpha:<REQUIRED_DB_PASSWORD>@#postgresql+psycopg://alpha:${DBPASS}@#" \
    -e "s#^ALPHA_CONTROL_TOKEN=.*#ALPHA_CONTROL_TOKEN=${CTOK}#" \
    "$APP/env"
fi

echo ">> 7/7 systemd 单元（仅装+启无凭据服务：监督/控制页）"
cp "$SRC"/deploy/systemd/alpha-*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable alpha-supervisor alpha-control-page >/dev/null 2>&1 || true
systemctl restart alpha-supervisor 2>/dev/null || systemctl start alpha-supervisor || true
systemctl restart alpha-control-page 2>/dev/null || systemctl start alpha-control-page || true

echo "bootstrap 完成 $(date -u)" >> "$LOG"
echo ""
echo "BOOTSTRAP_PRIMARY_DONE host=$(hostname) py=$($PY --version 2>&1)"
echo ">> 无凭据服务已起:alpha-supervisor / alpha-control-page（失败关闭型,缺 token 不空跑）"
echo ">> 72h 烤机由 deploy/start_soak_host.sh 单独拉起（自足 sqlite+假适配器,不需券商）"
echo ">> BLK-005(owner)待填 /opt/alpha/env:moomoo/Gmail 后 -> alpha-opend/trading/notify + 真实探针"
