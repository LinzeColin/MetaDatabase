#!/usr/bin/env bash
# Signal Lattice v2 部署入口（在生产机上 sudo 执行，工作目录任意）。
# 构建 wheel -> 安装到 /opt/signal-lattice-v2/releases/<版本> 并切 current -> 安装并启动 systemd 单元。
# 注意：scripts/deploy_v19_15s.sh 部署的是 v19 冻结 fixture 版本，不是本入口。
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${SIGNAL_LATTICE_PYTHON:-python3}"
[[ $EUID -eq 0 ]] || { echo "需要 root 权限：sudo bash $0" >&2; exit 2; }

id -u signal-lattice >/dev/null 2>&1 || useradd --system --home-dir /var/lib/signal-lattice-v2 --shell /usr/sbin/nologin signal-lattice
install -d -o signal-lattice -g signal-lattice -m 0750 /var/lib/signal-lattice-v2
install -d -m 0755 /etc/signal-lattice-v2
if [[ ! -f /etc/signal-lattice-v2/runtime.env ]]; then
  cat > /etc/signal-lattice-v2/runtime.env <<'ENV'
SIGNAL_LATTICE_STATE_DIR=/var/lib/signal-lattice-v2
SIGNAL_LATTICE_WEB_DIR=/opt/signal-lattice-v2/current/web
SIGNAL_LATTICE_HOST=127.0.0.1
SIGNAL_LATTICE_PORT=8787
ENV
fi

WHEEL_DIR="$(mktemp -d)"
trap 'rm -rf "$WHEEL_DIR"' EXIT
"$PYTHON" "$PROJECT_ROOT/scripts/build_wheel.py" --root "$PROJECT_ROOT" --output-dir "$WHEEL_DIR" --receipt "$WHEEL_DIR/wheel.json"
bash "$PROJECT_ROOT/scripts/install_release.sh" "$WHEEL_DIR"/signal_lattice-*.whl

install -m 0644 "$PROJECT_ROOT/deploy/systemd-v2/signal-lattice-v2-api.service" \
  "$PROJECT_ROOT/deploy/systemd-v2/signal-lattice-v2-loop.service" \
  "$PROJECT_ROOT/deploy/systemd-v2/signal-lattice-v2-loop.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable signal-lattice-v2-api.service signal-lattice-v2-loop.timer
systemctl restart signal-lattice-v2-api.service
systemctl start signal-lattice-v2-loop.timer
systemctl start signal-lattice-v2-loop.service || echo "首轮采集未得到 DATA_READY（休市或数据源异常），查看：journalctl -u signal-lattice-v2-loop -n 50" >&2
curl -fsS http://127.0.0.1:8787/health/live
echo
