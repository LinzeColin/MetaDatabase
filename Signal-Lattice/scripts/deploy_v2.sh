#!/usr/bin/env bash
# Signal Lattice v2 部署入口（在生产机上 sudo 执行，工作目录任意）。
# 构建 wheel -> 安装到 /opt/signal-lattice-v2/releases/<版本> 并切 current -> 安装并启动 systemd 单元。
# 注意：scripts/deploy_v19_15s.sh 部署的是 v19 冻结 fixture 版本，不是本入口。
# 两段式（新版本研究层要先预取 SEC 数据，成功后再切实时层）：
#   SIGNAL_LATTICE_STAGE_ONLY=1 sudo -E bash deploy_v2.sh   # 第一段：装 release 与单元，不切 current、不动在跑的服务
#   （用 systemd-run 在新 release 上跑一次 research，见 文档/06_运维手册.md 第 6 节）
#   sudo bash deploy_v2.sh                                    # 第二段：同一份代码再跑一遍 = 幂等切换 current 并启动全部 timer
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${SIGNAL_LATTICE_PYTHON:-python3}"
[[ $EUID -eq 0 ]] || { echo "需要 root 权限：sudo bash $0" >&2; exit 2; }

id -u signal-lattice >/dev/null 2>&1 || useradd --system --home-dir /var/lib/signal-lattice-v2 --shell /usr/sbin/nologin signal-lattice
STAGE_ONLY="${SIGNAL_LATTICE_STAGE_ONLY:-0}"
install -d -o signal-lattice -g signal-lattice -m 0750 /var/lib/signal-lattice-v2
install -d -o signal-lattice -g signal-lattice -m 0750 /var/lib/signal-lattice-v2/research /var/lib/signal-lattice-v2/research/work /var/lib/signal-lattice-v2/research/out /var/lib/signal-lattice-v2/backtest
install -d -m 0755 /etc/signal-lattice-v2
if [[ ! -f /etc/signal-lattice-v2/runtime.env ]]; then
  cat > /etc/signal-lattice-v2/runtime.env <<'ENV'
SIGNAL_LATTICE_STATE_DIR=/var/lib/signal-lattice-v2
SIGNAL_LATTICE_WEB_DIR=/opt/signal-lattice-v2/current/web
SIGNAL_LATTICE_HOST=127.0.0.1
SIGNAL_LATTICE_PORT=8787
ENV
fi

# 研究层向 SEC 取数必须声明联系方式：值由运维在服务器上写进这个 root:root 0600 文件，不进仓库、不进日志。
# 缺值时研究层直接报错退出，不发任何请求。
if [[ ! -f /etc/signal-lattice-v2/research.env ]]; then
  install -m 0600 -o root -g root /dev/null /etc/signal-lattice-v2/research.env
  echo "# SIGNAL_LATTICE_SEC_UA=<项目名 联系邮箱>   （必填，见 文档/06_运维手册.md）" > /etc/signal-lattice-v2/research.env
fi

WHEEL_DIR="$(mktemp -d)"
trap 'rm -rf "$WHEEL_DIR"' EXIT
"$PYTHON" "$PROJECT_ROOT/scripts/build_wheel.py" --root "$PROJECT_ROOT" --output-dir "$WHEEL_DIR" --receipt "$WHEEL_DIR/wheel.json"
bash "$PROJECT_ROOT/scripts/install_release.sh" "$WHEEL_DIR"/signal_lattice-*.whl

UNIT_DIR="$PROJECT_ROOT/deploy/systemd-v2"
install -m 0644 "$UNIT_DIR/signal-lattice-v2-api.service" "$UNIT_DIR/signal-lattice-v2-loop.service" \
  "$UNIT_DIR/signal-lattice-v2-loop.timer" "$UNIT_DIR/signal-lattice-v2-research.service" \
  "$UNIT_DIR/signal-lattice-v2-research.timer" "$UNIT_DIR/signal-lattice-v2-research-failed.service" \
  "$UNIT_DIR/signal-lattice-v2-backtest.service" "$UNIT_DIR/signal-lattice-v2-backtest.timer" /etc/systemd/system/
systemctl daemon-reload
if [[ "$STAGE_ONLY" == "1" ]]; then
  echo "STAGED：release 与单元已就绪，current 未切换，在跑的服务未动。下一步见 文档/06_运维手册.md 第 6 节。"
  exit 0
fi
systemctl enable signal-lattice-v2-research.timer signal-lattice-v2-backtest.timer
systemctl start signal-lattice-v2-research.timer signal-lattice-v2-backtest.timer
systemctl enable signal-lattice-v2-api.service signal-lattice-v2-loop.timer
systemctl restart signal-lattice-v2-api.service
systemctl start signal-lattice-v2-loop.timer
systemctl start signal-lattice-v2-loop.service || echo "首轮采集未得到 DATA_READY（休市或数据源异常），查看：journalctl -u signal-lattice-v2-loop -n 50" >&2
curl -fsS http://127.0.0.1:8787/health/live
echo
