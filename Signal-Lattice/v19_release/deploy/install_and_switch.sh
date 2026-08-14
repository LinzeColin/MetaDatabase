#!/usr/bin/env bash
set -euo pipefail
umask 027

[[ "$(id -u)" -eq 0 ]] || { echo ROOT_REQUIRED >&2; exit 2; }

VERSION="0.0.0.1.42"
PROMPT_VERSION="v0.0.0.19"
SOURCE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_ROOT="/opt/signal-lattice-v19"
RELEASE="$INSTALL_ROOT/releases/$VERSION"
CURRENT="$INSTALL_ROOT/current"
STATE_DIR="/var/lib/signal-lattice-v19"
DEPLOY_DIR="$STATE_DIR/deployment"
ENV_DIR="/etc/signal-lattice-v19"
ENV_FILE="$ENV_DIR/runtime.env"
LOCAL_URL="http://127.0.0.1:8787"
PUBLIC_URL="https://signal-lattice.linzezhang.com"
WHEEL="$(find "$SOURCE_ROOT/dist" -maxdepth 1 -type f -name 'signal_lattice_v19-0.0.0.1.42-*.whl' -print -quit)"

[[ -n "$WHEEL" && -f "$WHEEL" ]] || { echo PREBUILT_WHEEL_MISSING >&2; exit 3; }

if ! id signal-lattice >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/signal-lattice --shell /usr/sbin/nologin signal-lattice
fi
install -d -m 0755 "$INSTALL_ROOT/releases"
install -d -m 0750 -o signal-lattice -g signal-lattice "$STATE_DIR" "$STATE_DIR/history" "$STATE_DIR/skills" "$DEPLOY_DIR"
install -d -m 0750 -o root -g signal-lattice "$ENV_DIR"

python3 - "$DEPLOY_DIR/previous_state.json" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

units = ("signal-lattice-api.service", "signal-lattice-cycle.timer", "signal-lattice-cloudflared.service")
state = {}
for unit in units:
    enabled = subprocess.run(["systemctl", "is-enabled", unit], text=True, capture_output=True)
    active = subprocess.run(["systemctl", "is-active", unit], text=True, capture_output=True)
    state[unit] = {
        "enabled": (enabled.stdout or enabled.stderr).strip(),
        "active": (active.stdout or active.stderr).strip(),
    }
path = Path(sys.argv[1])
path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
PY

failure() {
  status=$?
  trap - ERR
  "$SOURCE_ROOT/deploy/collect_failure_facts.sh" >/dev/null 2>&1 || true
  "$SOURCE_ROOT/deploy/rollback.sh" >/dev/null 2>&1 || true
  echo "DEPLOYMENT_FAILED; facts=$DEPLOY_DIR/FAILURE_FACTS.txt" >&2
  exit "$status"
}
trap failure ERR

if [[ -d "$RELEASE" && ! -f "$RELEASE/release.json" ]]; then
  rm -rf "$RELEASE"
fi
if [[ ! -d "$RELEASE" ]]; then
  install -d -m 0755 "$RELEASE"
  python3 -m venv "$RELEASE/venv"
  "$RELEASE/venv/bin/python" -m pip install --no-index --no-deps "$WHEEL"
  cp -a "$SOURCE_ROOT/web" "$RELEASE/web"
  cp -a "$SOURCE_ROOT/config" "$RELEASE/config"
  cp -a "$SOURCE_ROOT/fixtures" "$RELEASE/fixtures"
  cp -a "$SOURCE_ROOT/scripts" "$RELEASE/scripts"
  cp -a "$SOURCE_ROOT/requirements" "$RELEASE/requirements"
  cp -a "$SOURCE_ROOT/deploy" "$RELEASE/deploy"
  python3 - "$RELEASE/release.json" "$VERSION" "$PROMPT_VERSION" <<'PY_RELEASE'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

out, version, prompt = sys.argv[1:]
payload = {
    "state": "INSTALLED_FILES_READY",
    "application_version": version,
    "decision_contract_version": prompt,
    "refresh_seconds": 15,
    "created_at": datetime.now(timezone.utc).isoformat(),
}
Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
PY_RELEASE
  chmod -R a+rX "$RELEASE"
fi

provider_available() {
  "$RELEASE/venv/bin/python" - <<'PY' >/dev/null 2>&1
try:
    import moomoo  # noqa: F401
except ImportError:
    import futu  # noqa: F401
PY
}

if ! provider_available; then
  OLD_PY="/opt/signal-lattice/current/venv/bin/python"
  if [[ -x "$OLD_PY" ]] && "$OLD_PY" - <<'PY' >/dev/null 2>&1
try:
    import moomoo  # noqa: F401
except ImportError:
    import futu  # noqa: F401
PY
  then
    OLD_SITE="$($OLD_PY - <<'PY'
import site
print(site.getsitepackages()[0])
PY
)"
    NEW_SITE="$($RELEASE/venv/bin/python - <<'PY'
import site
print(site.getsitepackages()[0])
PY
)"
    printf '%s\n' "$OLD_SITE" > "$NEW_SITE/signal_lattice_existing_provider.pth"
  else
    "$RELEASE/venv/bin/python" -m pip install -r "$RELEASE/requirements/providers-moomoo.txt"
  fi
fi
provider_available || { echo MOOMOO_QUOTE_PROVIDER_UNAVAILABLE >&2; exit 4; }

MOOMOO_HOST="127.0.0.1"
MOOMOO_PORT="11111"
OLD_ENV="/etc/signal-lattice/runtime.env"
if [[ -f "$OLD_ENV" ]]; then
  VALUE="$(awk -F= '$1=="MOOMOO_OPEND_HOST"{print $2; exit}' "$OLD_ENV" | tr -d '[:space:]')"
  [[ "$VALUE" =~ ^(127\.0\.0\.1|localhost|::1)$ ]] && MOOMOO_HOST="$VALUE"
  VALUE="$(awk -F= '$1=="MOOMOO_OPEND_PORT"{print $2; exit}' "$OLD_ENV" | tr -d '[:space:]')"
  [[ "$VALUE" =~ ^[0-9]{1,5}$ ]] && MOOMOO_PORT="$VALUE"
fi

cat > "$ENV_FILE" <<ENV
SL19_STATE_DIR=$STATE_DIR
SL19_CONFIG_DIR=$RELEASE/config
SL19_WEB_DIR=$RELEASE/web
SL19_FIXTURE_DIR=$RELEASE/fixtures
SL19_HOST=127.0.0.1
SL19_PORT=8787
SL19_REFRESH_SECONDS=15
SL19_MARKET_PROVIDER=moomoo
SL19_PUBLIC_URL=$PUBLIC_URL
SL19_STATUS_URL=https://status.linzezhang.com
MOOMOO_OPEND_HOST=$MOOMOO_HOST
MOOMOO_OPEND_PORT=$MOOMOO_PORT
PYTHONUNBUFFERED=1
ENV
chown root:signal-lattice "$ENV_FILE"
chmod 0640 "$ENV_FILE"

ln -sfn "$RELEASE" "$INSTALL_ROOT/current.new"
mv -Tf "$INSTALL_ROOT/current.new" "$CURRENT"

as_runtime_user() {
  runuser -u signal-lattice -- bash -c "set -a; source '$ENV_FILE'; set +a; exec \"\$@\"" -- "$@"
}

as_runtime_user "$CURRENT/venv/bin/signal-lattice-v19" bootstrap >/dev/null
as_runtime_user "$CURRENT/venv/bin/signal-lattice-v19" once >/dev/null

install -m 0644 "$SOURCE_ROOT/deploy/systemd/signal-lattice-v19-api.service" /etc/systemd/system/signal-lattice-v19-api.service
install -m 0644 "$SOURCE_ROOT/deploy/systemd/signal-lattice-v19-loop.service" /etc/systemd/system/signal-lattice-v19-loop.service
install -m 0644 "$SOURCE_ROOT/deploy/systemd/signal-lattice-v19-cloudflared.service" /etc/systemd/system/signal-lattice-v19-cloudflared.service
systemctl daemon-reload

# The existing tunnel unit requires the old API unit. Stop it before the API
# switch, then start the V19 tunnel service with the same existing token file.
systemctl disable --now signal-lattice-cloudflared.service 2>/dev/null || true
systemctl disable --now signal-lattice-cycle.timer 2>/dev/null || true
systemctl stop signal-lattice-api.service 2>/dev/null || true
systemctl enable --now signal-lattice-v19-api.service
systemctl enable --now signal-lattice-v19-loop.service
systemctl enable --now signal-lattice-v19-cloudflared.service

for _ in $(seq 1 20); do
  curl -fsS --max-time 4 "$LOCAL_URL/health/ready" >/dev/null 2>&1 && break
  sleep 2
done
"$CURRENT/venv/bin/python" "$CURRENT/scripts/run_acceptance.py" \
  --base-url "$LOCAL_URL" --verify-cadence --output "$DEPLOY_DIR/local_acceptance.json"

PUBLIC_PASS=0
for _ in $(seq 1 3); do
  if "$CURRENT/venv/bin/python" "$CURRENT/scripts/run_acceptance.py" \
      --base-url "$PUBLIC_URL" --verify-cadence --skip-stream --output "$DEPLOY_DIR/public_acceptance.json" >/dev/null 2>&1; then
    PUBLIC_PASS=1
    break
  fi
  sleep 5
done
[[ "$PUBLIC_PASS" -eq 1 ]] || { echo PUBLIC_ACCEPTANCE_FAILED >&2; false; }

python3 - "$DEPLOY_DIR/DELIVERY_RESULT.json" "$VERSION" "$PROMPT_VERSION" "$PUBLIC_URL" <<'PY'
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

out, version, prompt, public_url = sys.argv[1:]
payload = {
    "state": "PASS",
    "version": version,
    "prompt_version": prompt,
    "refresh_seconds": 15,
    "public_url": public_url,
    "local_url": "http://127.0.0.1:8787",
    "automatic_trading": False,
    "shadow_only": True,
    "api_unit": subprocess.run(["systemctl", "is-active", "signal-lattice-v19-api.service"], text=True, capture_output=True).stdout.strip(),
    "loop_unit": subprocess.run(["systemctl", "is-active", "signal-lattice-v19-loop.service"], text=True, capture_output=True).stdout.strip(),
    "tunnel_unit": subprocess.run(["systemctl", "is-active", "signal-lattice-v19-cloudflared.service"], text=True, capture_output=True).stdout.strip(),
    "deployed_at": datetime.now(timezone.utc).isoformat(),
}
Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
PY
chown signal-lattice:signal-lattice "$DEPLOY_DIR"/*.json 2>/dev/null || true
chmod 0640 "$DEPLOY_DIR"/*.json 2>/dev/null || true
trap - ERR
cat "$DEPLOY_DIR/DELIVERY_RESULT.json"
